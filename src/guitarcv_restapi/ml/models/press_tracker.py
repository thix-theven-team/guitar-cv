class PressTracker:
    """Регистрирует событие, только если набор (струна, лад) держится >= min_stable кадров."""
    def __init__(self, min_stable):
        self.min_stable = min_stable
        self.streak, self.first_seen = {}, {}
        self.events, self.current = [], None

    def update(self, t, keys):
        keys = set(keys)

        for k in list(self.streak):
            if k not in keys:
                del self.streak[k], self.first_seen[k]

        for k in keys:
            if k not in self.streak:
                self.streak[k] = 0
                self.first_seen[k] = t
            self.streak[k] += 1

        stable = frozenset(k for k, c in self.streak.items() if c >= self.min_stable)
        if self.current is not None and stable != self.current["keys"]:
            self._close(t)
        if self.current is None and stable:
            self.current = {"start": min(self.first_seen[k] for k in stable), "keys": stable}

    def _close(self, t):
        c = self.current
        if c is not None and t > c["start"]:
            self.events.append({"start_sec": round(c["start"], 3), "end_sec": round(t, 3),
                                "pressed": [{"string": s, "fret": f} for s, f in sorted(c["keys"])]})
        self.current = None

    def finish(self, t):
        self._close(t)
