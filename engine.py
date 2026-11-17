# Tiny chess engine: 0x88 board, negamax + quiescence, TT, fixed node budget.
import json
import os
import sys
import urllib.error
import urllib.request

ENV = os.environ.get("MAKEFUN_ENV_URL")
VAL = [0, 100, 320, 330, 500, 900, 0]
KN = [14, 18, 31, 33, -14, -18, -31, -33]
KI = [1, -1, 16, -16, 15, 17, -15, -17]
BD = [15, 17, -15, -17]
RD = [1, -1, 16, -16]
MATE = 100000
LIMIT = 50000  # nodes per move
CAP, EP, CA, DBL = 1 << 17, 1 << 18, 1 << 19, 1 << 20


def _pst():
    t = [[0] * 64 for _ in range(8)]
    pa = [0, 0, 4, 8, 14, 24, 40, 0]
    pc = [0, 0, 0, 10, 15, 10, 5, 0]
    for r in range(8):
        for f in range(8):
            i = r * 8 + f
            c = min(f, 7 - f) + min(r, 7 - r)
            t[1][i] = pa[r] + (pc[r] if f in (3, 4) else 0)
            t[2][i] = 6 * c - 20
            t[3][i] = 4 * c - 8
            t[4][i] = (15 if r == 6 else 0) + (5 if r == 0 and f in (3, 4) else 0)
            t[5][i] = 2 * c - 6
            t[6][i] = [20, 25, 10, 0, 0, 10, 25, 20][f] if r == 0 else max(-50, -15 * r)
    return t


PST = _pst()


def kh(p):
    # Position key: hash of board + side + castling + ep (stable each run).
    return hash((tuple(p.b), p.s, p.c, p.e))


TT = {}
N = 0
HIST = set()  # keys of the positions played so far


class Abort(Exception):
    pass


class Pos:
    __slots__ = ("b", "s", "c", "e", "k", "u", "np")

    def __init__(self):
        self.b = [0] * 128
        self.s = 0
        self.c = 0
        self.e = -1
        self.k = [4, 116]
        self.u = []
        self.np = 0

    def parse(self, fen):
        w = fen.split()
        rows = w[0].split("/")
        self.b = [0] * 128
        np = 0
        for i, row in enumerate(rows):
            r = 7 - i
            f = 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                else:
                    code = "PNBRQK".index(ch.upper()) + 1
                    if ch.islower():
                        code += 8
                    sq = r * 16 + f
                    self.b[sq] = code
                    if code & 7 == 6:
                        self.k[code >> 3] = sq
                    elif code & 7 != 1:
                        np += VAL[code & 7]
                    f += 1
        self.s = 0 if w[1] == "w" else 1
        self.c = 0
        if len(w) > 2:
            for ch, bit in (("K", 1), ("Q", 2), ("k", 4), ("q", 8)):
                if ch in w[2]:
                    self.c |= bit
        self.e = -1
        if len(w) > 3 and w[3] != "-":
            self.e = (int(w[3][1]) - 1) * 16 + "abcdefgh".index(w[3][0])
        self.np = np
        self.u = []

    def atk(self, sq, by):
        b = self.b
        d = -16 if by == 0 else 16
        for t in (sq + d - 1, sq + d + 1):
            if not t & 0x88 and b[t] == 1 | by << 3:
                return True
        for ds, pc in ((KN, 2), (KI, 6)):
            for d in ds:
                t = sq + d
                if not t & 0x88 and b[t] == pc | by << 3:
                    return True
        for ds, pcs in ((BD, (3, 5)), (RD, (4, 5))):
            for d in ds:
                t = sq + d
                while not t & 0x88:
                    q = b[t]
                    if q:
                        if q >> 3 == by and q & 7 in pcs:
                            return True
                        break
                    t += d
        return False

    def gen(self, caps=False):
        ms = []
        b = self.b
        s = self.s
        d = 16 if s == 0 else -16
        r0 = 1 if s == 0 else 6
        r7 = 6 if s == 0 else 1
        for sq in range(128):
            if sq & 0x88:
                continue
            p = b[sq]
            if not p or p >> 3 != s:
                continue
            t = p & 7
            if t == 1:
                one = sq + d
                if not one & 0x88 and not b[one] and not caps:
                    if sq >> 4 == r7:
                        for pr in (5, 4, 3, 2):
                            ms.append(sq | one << 7 | pr << 14)
                    else:
                        ms.append(sq | one << 7)
                        if sq >> 4 == r0:
                            two = sq + 2 * d
                            if not b[two]:
                                ms.append(sq | two << 7 | DBL)
                for dd in (d - 1, d + 1):
                    to = sq + dd
                    if to & 0x88:
                        continue
                    q = b[to]
                    if q and q >> 3 != s:
                        if sq >> 4 == r7:
                            for pr in (5, 4, 3, 2):
                                ms.append(sq | to << 7 | pr << 14 | CAP)
                        else:
                            ms.append(sq | to << 7 | CAP)
                    elif to == self.e:
                        ms.append(sq | to << 7 | CAP | EP)
            elif t == 2 or t == 6:
                for dd in KN if t == 2 else KI:
                    to = sq + dd
                    if to & 0x88:
                        continue
                    q = b[to]
                    if not q:
                        if not caps:
                            ms.append(sq | to << 7)
                    elif q >> 3 != s:
                        ms.append(sq | to << 7 | CAP)
                if t == 6 and sq == (4 if s == 0 else 116):
                    # (direction, rights bit, empty offsets from the king)
                    for sgn, bit, emp in ((1, 1 if s == 0 else 4, (1, 2)),
                                          (-1, 2 if s == 0 else 8, (1, 2, 3))):
                        if (self.c & bit and not any(b[sq + sgn * k] for k in emp)
                                and not any(self.atk(sq + sgn * k, s ^ 1) for k in (0, 1, 2))):
                            ms.append(sq | (sq + sgn * 2) << 7 | CA)
            else:
                for dd in BD if t == 3 else RD if t == 4 else BD + RD:
                    to = sq + dd
                    while not to & 0x88:
                        q = b[to]
                        if not q:
                            if not caps:
                                ms.append(sq | to << 7)
                        else:
                            if q >> 3 != s:
                                ms.append(sq | to << 7 | CAP)
                            break
                        to += dd
        return ms

    def leg(self):
        out = []
        for m in self.gen():
            self.make(m)
            if not self.atk(self.k[self.s ^ 1], self.s):
                out.append(m)
            self.undo()
        return out

    def make(self, m):
        b = self.b
        f = m & 127
        t = m >> 7 & 127
        pr = m >> 14 & 7
        p = b[f]
        cp = 0
        if m & EP:
            cs = t - 16 if self.s == 0 else t + 16
            cp = b[cs]
            b[cs] = 0
        elif b[t]:
            cp = b[t]
        self.u.append((m, cp, self.c, self.e, self.k[0], self.k[1], self.np))
        if cp and (cp & 7) != 1:
            self.np -= VAL[cp & 7]
        if pr:
            self.np += VAL[pr]
        b[f] = 0
        b[t] = pr | self.s << 3 if pr else p
        if p & 7 == 6:
            self.k[self.s] = t
            if m & CA:
                self._rk(f, t)
        nc = self.c
        if p & 7 == 6:
            nc &= ~(3 if self.s == 0 else 12)
        for q, bit in ((0, 2), (7, 1), (112, 8), (119, 4)):
            if f == q or t == q:
                nc &= ~bit
        self.c = nc
        if m & DBL:
            self.e = (f + t) // 2
        else:
            self.e = -1
        self.s ^= 1

    def _rk(self, f, t, back=False):
        # Move the rook of a castling king move (back: undo it).
        a, b = (f + 3, f + 1) if t > f else (f - 4, f - 1)
        if back:
            a, b = b, a
        r = self.b[a]
        self.b[a] = 0
        self.b[b] = r

    def undo(self):
        m, cp, c0, e0, k0, k1, np0 = self.u.pop()
        f = m & 127
        t = m >> 7 & 127
        pr = m >> 14 & 7
        self.s ^= 1
        p = self.b[t]
        self.b[t] = 0
        if m & EP:
            cs = t - 16 if self.s == 0 else t + 16
            self.b[cs] = cp
        elif cp:
            self.b[t] = cp
        self.b[f] = 1 | self.s << 3 if pr else p
        if m & CA:
            self._rk(f, t, True)
        self.c, self.e, self.k[0], self.k[1], self.np = c0, e0, k0, k1, np0

    def ev(self):
        b = self.b
        sc = 0
        ka = [0, 0]
        for sq, p in enumerate(b):
            if sq & 0x88 or not p:
                continue
            t = p & 7
            c = p >> 3
            r = sq >> 4
            f = sq & 7
            if t == 6:
                ka[c] = r * 8 + f if c == 0 else (7 - r) * 8 + f
                continue
            rel = r * 8 + f if c == 0 else (7 - r) * 8 + f
            v = VAL[t] + PST[t][rel]
            sc += v if c == 0 else -v
        sc += PST[6][ka[0]] - PST[6][ka[1]]
        return sc if self.s == 0 else -sc


def order(p, ms, ttmove):
    def key(m):
        if m == ttmove:
            return 1 << 28
        v = 0
        t = m >> 7 & 127
        q = p.b[t]
        if m & CAP:
            v = (100 if m & EP else VAL[q & 7]) * 16 - VAL[p.b[m & 127] & 7]
        if m >> 14 & 7:
            v += 900
        return v
    ms.sort(key=key, reverse=True)


def qs(p, al, be, ply):
    global N
    N += 1
    if N >= LIMIT:
        raise Abort
    if ply >= 100:
        return p.ev()
    chk = p.atk(p.k[p.s], p.s ^ 1)
    if chk:
        ms = p.leg()
        if not ms:
            return -MATE + ply
    else:
        stand = p.ev()
        if stand >= be:
            return be
        if stand > al:
            al = stand
        ms = []
        for m in p.gen(caps=True):
            p.make(m)
            if not p.atk(p.k[p.s ^ 1], p.s):
                ms.append(m)
            p.undo()
    order(p, ms, 0)
    for m in ms:
        p.make(m)
        s = -qs(p, -be, -al, ply + 1)
        p.undo()
        if s >= be:
            return be
        if s > al:
            al = s
    return al


def srch(p, d, al, be, ply, null_ok=True):
    global N
    N += 1
    if N >= LIMIT:
        raise Abort
    k = kh(p)
    if k in HIST:
        return 0
    if d <= 0:
        return qs(p, al, be, ply)
    e = TT.get(k)
    ttm = 0
    if e and e[0] >= d:
        s = e[1] - ply if e[1] > MATE - 256 else e[1] + ply if e[1] < -MATE + 256 else e[1]
        if e[2] == 1:
            return s
        if e[2] == 2 and s >= be:
            return s
        if e[2] == 3 and s <= al:
            return s
        ttm = e[3]
    chk = p.atk(p.k[p.s], p.s ^ 1)
    ms = p.leg()
    if not ms:
        return -MATE + ply if chk else 0
    if d >= 3 and null_ok and not chk and p.np > 600:
        # Null move: pass, switching side (only ep square and side change).
        e0 = p.e
        p.e = -1
        p.s ^= 1
        s = -srch(p, d - 3, -be, -be + 1, ply + 1, False)
        p.e = e0
        p.s ^= 1
        if s >= be:
            return be
    order(p, ms, ttm)
    best = -MATE
    bm = 0
    ao = al
    for m in ms:
        p.make(m)
        s = -srch(p, d - 1, -be, -al, ply + 1)
        p.undo()
        if s > best:
            best = s
            bm = m
        if s > al:
            al = s
        if al >= be:
            break
    if len(TT) > 500000:
        TT.clear()
    s = best + ply if best > MATE - 256 else best - ply if best < -MATE + 256 else best
    TT[k] = (d, s, 2 if best >= be else 3 if best <= ao else 1, bm)
    return best


def root(p, ms):
    if len(ms) == 1:
        return ms[0]
    global N
    N = 0
    best = ms[0]
    prev = {}
    try:
        for d in range(1, 65):
            ms.sort(key=lambda m: -prev.get(m, 0))
            al = -MATE
            cur = ms[0]
            cs = -MATE
            for m in ms:
                p.make(m)
                s = -srch(p, d - 1, -MATE, -al, 1)
                p.undo()
                prev[m] = s
                if s > cs:
                    cs, cur = s, m
                if s > al:
                    al = s
            best = cur
    except Abort:
        pass
    return best


def uci(m):
    f = m & 127
    t = m >> 7 & 127
    pr = m >> 14 & 7
    s = "abcdefgh"[f & 7] + str((f >> 4) + 1) + "abcdefgh"[t & 7] + str((t >> 4) + 1)
    return s + "nbrq"[pr - 2] if pr else s


START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def post(path, body):
    if not ENV:
        sys.exit("MAKEFUN_ENV_URL is not set")
    req = urllib.request.Request(ENV + path, data=json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        sys.exit(f"{path}: HTTP {e.code}")


def replay(hp, moves):
    # Rebuild the game history: hp follows the moves, HIST takes each key.
    HIST.clear()
    hp.parse(START)
    for u in moves:
        for m in hp.leg():
            if uci(m) == u:
                hp.make(m)
                HIST.add(kh(hp))
                break


def main():
    p = Pos()
    hp = Pos()
    game = 0
    while True:
        g = post("/game", {})
        if g["status"] == "done":
            break
        if g["game"] != game:
            game = g["game"]
            TT.clear()
        while g["status"] == "your_move":
            replay(hp, g["moves"])
            p.parse(g["fen"])
            m = root(p, p.leg())
            u = uci(m)
            if u not in g["legal_moves"]:
                u = g["legal_moves"][0]
            g = post("/move", {"game": g["game"], "move": u})


if __name__ == "__main__":
    main()
