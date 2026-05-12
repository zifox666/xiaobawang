"""
自动分组算法 — 将击杀邮件中的势力自动分配到队伍。
Python port of BattleReportAnalyzer.performAutoTeaming() from warbeacon.net.
"""
from __future__ import annotations

from collections import defaultdict
from math import log

# 敌对/合作判定阈值
HOSTILITY_THRESHOLD = 0.1
COOPERATION_THRESHOLD = 0.2
MAX_TEAMS = 8


def faction_key(alliance_id: int | None, corporation_id: int | None) -> str | None:
    """优先用 alliance，其次用 corporation，二者均无则返回 None。"""
    if alliance_id:
        return f"alliance_{alliance_id}"
    if corporation_id:
        return f"corporation_{corporation_id}"
    return None


class _BRGrouper:
    """内部分组器，完整移植 warbeacon.net 的分组算法。"""

    def __init__(self) -> None:
        # fkey -> {participants: set[char_id], total_value, damage_dealt, damage_received}
        self.faction_map: dict[str, dict] = {}
        # attacker_key -> target_key -> isk_value_contribution
        self.attack_target_matrix: dict[str, dict[str, float]] = {}
        # (min_key, max_key) -> {km_ids: set, score: float}
        self.direct_coop_matrix: dict[tuple[str, str], dict] = {}
        # frozenset of (k1, k2) hostile pairs
        self.hostile_relationships: set[tuple[str, str]] = set()
        # corp_key -> alliance_key
        self._corp_alliance_map: dict[str, str] = {}
        self.grand_total_value: float = 0.0

    # ------------------------------------------------------------------ helpers

    def _pair_key(self, k1: str, k2: str) -> tuple[str, str]:
        return (k1, k2) if k1 < k2 else (k2, k1)

    def _is_hostile_pair(self, k1: str, k2: str) -> bool:
        return self._pair_key(k1, k2) in self.hostile_relationships

    def _coop_score(self, k1: str, k2: str) -> float:
        entry = self.direct_coop_matrix.get(self._pair_key(k1, k2))
        return entry["score"] if entry else 0.0

    def _ensure_faction(self, alliance_id: int | None, corporation_id: int | None) -> str | None:
        fkey = faction_key(alliance_id, corporation_id)
        if not fkey:
            return None
        if alliance_id and corporation_id:
            ck = f"corporation_{corporation_id}"
            ak = f"alliance_{alliance_id}"
            self._corp_alliance_map[ck] = ak
        if fkey not in self.faction_map:
            self.faction_map[fkey] = {
                "participants": set(),
                "total_value": 0.0,
                "damage_dealt": 0,
                "damage_received": 0,
                "kills_count": 0,
            }
        return fkey

    # ------------------------------------------------------------------ parsing

    def parse_killmails(self, killmails: list[dict]) -> None:
        for km in killmails:
            km_value = float(km.get("total_value", 0))
            attackers = km.get("attackers", [])
            total_damage = sum(a.get("damage_done", 0) for a in attackers)
            self.grand_total_value += km_value

            victim = km.get("victim", {})
            v_key = self._ensure_faction(victim.get("alliance_id"), victim.get("corporation_id"))
            if not v_key:
                continue

            vfac = self.faction_map[v_key]
            if victim.get("character_id"):
                vfac["participants"].add(victim["character_id"])
            vfac["total_value"] += km_value
            vfac["damage_received"] += total_damage

            effective: dict[str, float] = {}  # fkey -> value_contribution

            for att in attackers:
                if not att.get("ship_type_id"):
                    continue
                a_key = self._ensure_faction(att.get("alliance_id"), att.get("corporation_id"))
                if not a_key:
                    continue

                afac = self.faction_map[a_key]
                if att.get("character_id"):
                    afac["participants"].add(att["character_id"])

                damage = att.get("damage_done", 0)
                base_contrib = km_value * 0.001
                dmg_contrib = (damage / (total_damage or 1)) * km_value
                value_contrib = max(dmg_contrib, base_contrib)

                afac["damage_dealt"] += damage
                if att.get("final_blow"):
                    afac["kills_count"] += 1

                atm = self.attack_target_matrix.setdefault(a_key, {})
                atm[v_key] = atm.get(v_key, 0.0) + value_contrib
                effective[a_key] = effective.get(a_key, 0.0) + value_contrib

            # 记录合作关系
            eff_keys = list(effective.keys())
            km_id = km.get("killmail_id", id(km))
            for i in range(len(eff_keys)):
                for j in range(i + 1, len(eff_keys)):
                    k1, k2 = eff_keys[i], eff_keys[j]
                    s1, s2 = effective[k1], effective[k2]
                    if s1 > 1 and s2 > 1:
                        score = (log(s1) / log(s2) if s1 > s2 else log(s2) / log(s1)) * km_value
                    else:
                        score = km_value * 0.001
                    pk = self._pair_key(k1, k2)
                    entry = self.direct_coop_matrix.setdefault(pk, {"km_ids": set(), "score": 0.0})
                    if km_id not in entry["km_ids"]:
                        entry["km_ids"].add(km_id)
                        entry["score"] += score

    # ------------------------------------------------------------------ hostility

    def _is_hostile(self, f1: str, f2: str) -> bool:
        t1 = self.attack_target_matrix.get(f1, {})
        t2 = self.attack_target_matrix.get(f2, {})
        a1 = t1.get(f2, 0.0)
        a2 = t2.get(f1, 0.0)

        if a1 == 0 and a2 == 0:
            return False
        if a1 + a2 < self.grand_total_value * 0.001:
            return False  # 误伤

        t1_total = sum(t1.values()) or 1.0
        t2_total = sum(t2.values()) or 1.0
        ratio1 = a1 / t1_total
        ratio2 = a2 / t2_total
        if ratio1 >= HOSTILITY_THRESHOLD or ratio2 >= HOSTILITY_THRESHOLD:
            return True

        f1_value = self.faction_map.get(f1, {}).get("total_value", 1.0) or 1.0
        f2_value = self.faction_map.get(f2, {}).get("total_value", 1.0) or 1.0
        if a2 / f1_value >= HOSTILITY_THRESHOLD or a1 / f2_value >= HOSTILITY_THRESHOLD:
            return True

        return False

    def detect_hostile_relationships(self) -> None:
        keys = list(self.faction_map.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if self._is_hostile(keys[i], keys[j]):
                    self.hostile_relationships.add(self._pair_key(keys[i], keys[j]))

    # ------------------------------------------------------------------ cooperation scores

    def calculate_cooperation_scores(self) -> dict[str, dict[str, float]]:
        # 构建 hostile neighbors 表
        hostile_nbrs: dict[str, set[str]] = defaultdict(set)
        for (k1, k2) in self.hostile_relationships:
            hostile_nbrs[k1].add(k2)
            hostile_nbrs[k2].add(k1)

        scores: dict[str, dict[str, float]] = {}
        all_factions = list(self.faction_map.keys())

        for f1 in all_factions:
            scores[f1] = {}
            for f2 in all_factions:
                if f1 == f2:
                    continue
                sc = 0.0

                # 共同敌对势力加分
                for enemy in hostile_nbrs.get(f1, set()):
                    if enemy in hostile_nbrs.get(f2, set()):
                        atk1 = self.attack_target_matrix.get(f1, {}).get(enemy, 0.0)
                        atk2 = self.attack_target_matrix.get(f2, {}).get(enemy, 0.0)
                        sc += 2.0 * (atk1 + atk2)

                # 直接合作
                if not self._is_hostile_pair(f1, f2):
                    sc += self._coop_score(f1, f2) * 2.0

                # 共同攻击目标
                t1 = self.attack_target_matrix.get(f1, {})
                t2 = self.attack_target_matrix.get(f2, {})
                for target in set(t1) & set(t2) - {f1, f2}:
                    if (not self._is_hostile_pair(f1, target)
                            and not self._is_hostile_pair(f2, target)):
                        sc += (t1[target] + t2[target]) * 1.0

                if sc > 0:
                    scores[f1][f2] = sc

        return scores

    # ------------------------------------------------------------------ merge helpers

    def _teams_have_conflict(self, t1: set[str], t2: set[str]) -> bool:
        return any(self._is_hostile_pair(f1, f2) for f1 in t1 for f2 in t2)

    def _teams_coop_score(
        self, t1: set[str], t2: set[str], coop: dict[str, dict[str, float]]
    ) -> float:
        total = 0.0
        for f1 in t1:
            for f2 in t2:
                s12 = coop.get(f1, {}).get(f2, 0.0)
                s21 = coop.get(f2, {}).get(f1, 0.0)
                total += (s12 + s21) / 2
        return total

    # ------------------------------------------------------------------ step 8: merge compatible

    def merge_compatible_teams(
        self, teams: list[set[str]], coop: dict[str, dict[str, float]]
    ) -> list[set[str]]:
        teams = [set(t) for t in teams]
        merged = True
        while merged and len(teams) > 1:
            merged = False
            best: tuple[int, int, float] | None = None
            for i in range(len(teams)):
                for j in range(i + 1, len(teams)):
                    if self._teams_have_conflict(teams[i], teams[j]):
                        continue
                    sc = self._teams_coop_score(teams[i], teams[j], coop)
                    if sc > 0 and (best is None or sc > best[2]):
                        best = (i, j, sc)
            if best:
                i, j, _ = best
                teams[i] |= teams[j]
                teams.pop(j)
                merged = True
        return teams

    # ------------------------------------------------------------------ step 9: optimize

    def optimize_team_assignments(
        self, teams: list[set[str]], coop: dict[str, dict[str, float]]
    ) -> list[set[str]]:
        teams = [set(t) for t in teams]
        solo_indices = [i for i in range(1, len(teams)) if len(teams[i]) == 1]

        for idx in solo_indices:
            if idx >= len(teams) or len(teams[idx]) != 1:
                continue
            fkey = next(iter(teams[idx]))
            fscores = coop.get(fkey, {})

            best_idx, best_sc, second_sc = -1, 0.0, 0.0
            for ti, team in enumerate(teams):
                if ti == idx:
                    continue
                if any(self._is_hostile_pair(fkey, m) for m in team):
                    continue
                sc = sum(fscores.get(m, 0.0) for m in team)
                if sc > best_sc:
                    second_sc = best_sc
                    best_sc = sc
                    best_idx = ti
                elif sc > second_sc:
                    second_sc = sc

            if best_sc > 0:
                # 如果与前两个团队合作分值接近，分配到团队7（独立小团队）
                if second_sc > 0 and 0.25 <= (best_sc / second_sc) <= 4.0:
                    while len(teams) <= 7:
                        teams.append(set())
                    teams[7].add(fkey)
                    teams[idx].discard(fkey)
                else:
                    teams[best_idx].add(fkey)
                    teams[idx].discard(fkey)

        return [t for t in teams if t]

    # ------------------------------------------------------------------ step 10: merge independent

    def merge_independent_teams(
        self, teams: list[set[str]], coop: dict[str, dict[str, float]]
    ) -> list[set[str]]:
        result = [set(t) for t in teams]
        independent: list[int] = []

        for i, team in enumerate(result):
            has_rel = False
            for j, other in enumerate(result):
                if i == j:
                    continue
                for f1 in team:
                    for f2 in other:
                        if (coop.get(f1, {}).get(f2, 0.0) > 0
                                or coop.get(f2, {}).get(f1, 0.0) > 0
                                or self._is_hostile_pair(f1, f2)):
                            has_rel = True
                            break
                    if has_rel:
                        break
                if has_rel:
                    break
            if not has_rel:
                independent.append(i)

        if len(independent) <= 1:
            return result

        first = independent[0]
        for i in reversed(independent[1:]):
            result[first] |= result[i]
            result.pop(i)
        return result

    # ------------------------------------------------------------------ step 11: max 8 teams

    def enforce_max_teams(
        self, teams: list[set[str]], coop: dict[str, dict[str, float]]
    ) -> list[set[str]]:
        teams = [set(t) for t in teams]
        while len(teams) > MAX_TEAMS:
            smallest = min(range(len(teams)), key=lambda i: len(teams[i]))
            best_target = -1
            best_sc = -1.0
            for i, team in enumerate(teams):
                if i == smallest:
                    continue
                if self._teams_have_conflict(teams[smallest], team):
                    continue
                sc = self._teams_coop_score(teams[smallest], team, coop)
                if sc > best_sc:
                    best_sc = sc
                    best_target = i

            if best_target == -1:
                # 强制合并最小两个团队
                sizes = sorted(range(len(teams)), key=lambda i: len(teams[i]))
                a, b = min(sizes[0], sizes[1]), max(sizes[0], sizes[1])
                teams[a] |= teams[b]
                teams.pop(b)
            else:
                if smallest < best_target:
                    teams[smallest] |= teams[best_target]
                    teams.pop(best_target)
                else:
                    teams[best_target] |= teams[smallest]
                    teams.pop(smallest)
        return teams

    # ------------------------------------------------------------------ main

    def perform_auto_teaming(self) -> list[set[str]]:
        if not self.faction_map:
            return []

        self.detect_hostile_relationships()
        coop = self.calculate_cooperation_scores()

        # 初始每个势力独立成队
        teams: list[set[str]] = [set([fkey]) for fkey in self.faction_map]

        # 合并可合并的团队
        teams = self.merge_compatible_teams(teams, coop)

        # 优化分配（把单独势力移到更合适的团队）
        teams = self.optimize_team_assignments(teams, coop)

        # 若多于2队，合并无关系的独立小团队
        if len(teams) > 2:
            teams = self.merge_independent_teams(teams, coop)

        # 强制不超过8队
        teams = self.enforce_max_teams(teams, coop)

        return teams


# ------------------------------------------------------------------ public API

def perform_auto_teaming(killmails: list[dict]) -> list[set[str]]:
    """
    对 killmails 进行自动队伍分组。
    返回 list[set[str]]，每个 set 内是该队伍的势力键（如 'alliance_99003581'）。
    """
    grouper = _BRGrouper()
    grouper.parse_killmails(killmails)
    return grouper.perform_auto_teaming()
