"""Deterministic flavor-name generation for students/applicants."""
from __future__ import annotations

GIVEN = ["Ari", "Bo", "Cam", "Dev", "Eli", "Fen", "Gus", "Hana", "Iris", "Jun",
         "Kai", "Lena", "Miko", "Noor", "Om", "Pia", "Quinn", "Ravi", "Sena", "Tao",
         "Uma", "Vik", "Wen", "Ximena", "Yara", "Zed", "Anouk", "Bram", "Cleo", "Darius"]
FAMILY = ["Alder", "Brook", "Chen", "Duarte", "Egede", "Farah", "Gao", "Haddad",
          "Ito", "Jansen", "Kovacs", "Lindqvist", "Moreau", "Nakamura", "Okafor",
          "Petrov", "Qureshi", "Rossi", "Sato", "Tanaka", "Ueda", "Varga", "Wong",
          "Xu", "Yilmaz", "Zhang", "Abara", "Bishop", "Costa", "Deng"]


def make_name(rng) -> str:
    return f"{GIVEN[int(rng.integers(len(GIVEN)))]} {FAMILY[int(rng.integers(len(FAMILY)))]}"
