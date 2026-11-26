def validate_team(team, student_lookup, rules):
    """Validate team size, member existence, and duplicate/multi-team issues."""
    errors = []
    members = team.get("members", [])
    min_size = rules["min_team_size"]
    max_size = rules["max_team_size"]

    if len(members) < min_size or len(members) > max_size:
        errors.append(f"Team size {len(members)} outside allowed range [{min_size}-{max_size}].")

    seen = []
    for m_id in members:
        if m_id not in student_lookup:
            errors.append(f"Unknown student ID: {m_id}.")
        elif m_id in seen:
            errors.append(f"Duplicate member in team: {m_id}.")
        else:
            seen.append(m_id)

    return len(errors) == 0, errors


def check_cross_team_duplicates(teams):
    """Return a set of student IDs appearing in more than one team."""
    counts = {}
    for team in teams:
        for m_id in team.get("members", []):
            counts[m_id] = counts.get(m_id, 0) + 1

    duplicates = set()
    for m_id, cnt in counts.items():
        if cnt > 1:
            duplicates.add(m_id)
    return duplicates


def aggregate_team_scores(team, student_lookup, round_weights):
    """
    Aggregate round-wise scores across team members.
    Supports both average or sum across members per round, plus weighted total.
    """
    members = team["members"]
    num_rounds = len(round_weights)
    round_totals = [0.0] * num_rounds
    round_averages = [0.0] * num_rounds

    for r_idx in range(num_rounds):
        r_sum = 0.0
        for m_id in members:
            r_sum += student_lookup[m_id]["scores"][r_idx]
        round_totals[r_idx] = round(r_sum, 2)
        round_averages[r_idx] = round(r_sum / len(members), 2) if members else 0.0

    # Weighted total using round averages (keeps team size fair across valid sizes)
    weighted_score = 0.0
    for r_idx, weight in enumerate(round_weights):
        weighted_score += round_averages[r_idx] * weight
    weighted_score = round(weighted_score, 2)

    total_raw_points = round(sum(round_totals), 2)
    final_round_avg = round_averages[-1] if round_averages else 0.0
    max_single_round_avg = max(round_averages) if round_averages else 0.0

    # Track composition (e.g., distinct branches/departments)
    branches = []
    for m_id in members:
        br = student_lookup[m_id]["branch"]
        if br not in branches:
            branches.append(br)

    return {
        "team_id": team["team_id"],
        "team_name": team["team_name"],
        "size": len(members),
        "branches": ", ".join(branches),
        "round_totals": round_totals,
        "round_averages": round_averages,
        "weighted_score": weighted_score,
        "total_raw_points": total_raw_points,
        "final_round_avg": final_round_avg,
        "max_single_round_avg": max_single_round_avg,
        "submission_minutes": team.get("submission_minutes", 9999),
    }


def is_better_ranked(a, b):
    """
    Tie-breaking comparison: returns True if team 'a' ranks ahead of team 'b'.
    Rules:
      1. Higher weighted_score
      2. Higher final_round_avg (later round performance)
      3. Higher max_single_round_avg (peak round score)
      4. Earlier submission_minutes (lower timestamp value wins)
      5. Lexicographical team_id for deterministic ordering
    """
    if a["weighted_score"] != b["weighted_score"]:
        return a["weighted_score"] > b["weighted_score"]
    if a["final_round_avg"] != b["final_round_avg"]:
        return a["final_round_avg"] > b["final_round_avg"]
    if a["max_single_round_avg"] != b["max_single_round_avg"]:
        return a["max_single_round_avg"] > b["max_single_round_avg"]
    if a["submission_minutes"] != b["submission_minutes"]:
        return a["submission_minutes"] < b["submission_minutes"]
    return a["team_id"] < b["team_id"]


def rank_teams(valid_team_records):
    """Sort valid team records using predefined tie-breakers and assign ranks."""
    ordered = list(valid_team_records)
    n = len(ordered)
    for i in range(n):
        for j in range(i + 1, n):
            if is_better_ranked(ordered[j], ordered[i]):
                ordered[i], ordered[j] = ordered[j], ordered[i]

    for idx, rec in enumerate(ordered):
        rec["rank"] = idx + 1

    return ordered


def print_hackathon_report(ranked_teams, invalid_reports, cross_duplicates):
    """Display validation warnings, team compositions, round aggregates, and final rankings."""
    print("=" * 104)
    print("HACKATHON TEAM VALIDATION & FINAL RANKINGS")
    print("=" * 104)

    if cross_duplicates:
        print(f"Cross-Team Duplicate Student IDs Detected: {', '.join(sorted(cross_duplicates))}")

    for item in invalid_reports:
        print(f"[DISQUALIFIED / INVALID] {item['team_id']} ({item['team_name']}): {' | '.join(item['errors'])}")

    if invalid_reports:
        print("-" * 104)

    print(
        f"{'Rank':>4} {'Team ID':<8} {'Team Name':<18} {'Size':>4} {'Branches':<12} "
        f"{'R1 Avg':>7} {'R2 Avg':>7} {'R3 Avg':>7} {'Weighted':>9} {'SubMin':>7}"
    )
    print("-" * 104)

    for t in ranked_teams:
        r_avgs = t["round_averages"]
        r1 = r_avgs[0] if len(r_avgs) > 0 else 0.0
        r2 = r_avgs[1] if len(r_avgs) > 1 else 0.0
        r3 = r_avgs[2] if len(r_avgs) > 2 else 0.0
        print(
            f"{t['rank']:>4} {t['team_id']:<8} {t['team_name']:<18} {t['size']:>4} {t['branches']:<12} "
            f"{r1:>7.2f} {r2:>7.2f} {r3:>7.2f} {t['weighted_score']:>9.2f} {t['submission_minutes']:>7}"
        )

    print("=" * 104 + "\n")


def main():
    rules = {
        "min_team_size": 2,
        "max_team_size": 4,
        "round_weights": [0.25, 0.35, 0.40],  # Round 1: 25%, Round 2: 35%, Round 3: 40%
    }

    students = [
        {"id": "S01", "name": "Aarav", "branch": "CSE", "scores": [80, 85, 90]},
        {"id": "S02", "name": "Bhavana", "branch": "ECE", "scores": [84, 85, 88]},
        {"id": "S03", "name": "Chetan", "branch": "CSE", "scores": [78, 82, 86]},
        {"id": "S04", "name": "Diya", "branch": "IT", "scores": [86, 88, 92]},
        {"id": "S05", "name": "Eshan", "branch": "CSE", "scores": [82, 82, 88]},
        {"id": "S06", "name": "Farah", "branch": "AIDS", "scores": [82, 88, 88]},
        {"id": "S07", "name": "Gaurav", "branch": "ECE", "scores": [70, 75, 80]},
        {"id": "S08", "name": "Harika", "branch": "IT", "scores": [90, 91, 94]},
    ]

    student_lookup = {s["id"]: s for s in students}

    teams = [
        {
            "team_id": "T01",
            "team_name": "CodeCrafters",
            "members": ["S01", "S02", "S03"],
            "submission_minutes": 142,
        },
        {
            "team_id": "T02",
            "team_name": "ByteBuilders",
            "members": ["S04", "S05"],
            "submission_minutes": 128,
        },
        {
            "team_id": "T03",
            "team_name": "LogicPulse",
            "members": ["S06", "S08"],
            "submission_minutes": 135,
        },
        {
            "team_id": "T04",
            "team_name": "SoloSpark",
            "members": ["S07"],  # Invalid: below min_team_size (2)
            "submission_minutes": 120,
        },
    ]

    cross_duplicates = check_cross_team_duplicates(teams)
    valid_records = []
    invalid_reports = []

    for team in teams:
        is_valid, errors = validate_team(team, student_lookup, rules)
        # Flag if any team member also appears in another team
        dup_in_other = [m for m in team.get("members", []) if m in cross_duplicates]
        if dup_in_other:
            is_valid = False
            errors.append(f"Member(s) in multiple teams: {', '.join(dup_in_other)}.")

        if is_valid:
            agg = aggregate_team_scores(team, student_lookup, rules["round_weights"])
            valid_records.append(agg)
        else:
            invalid_reports.append({
                "team_id": team.get("team_id", "N/A"),
                "team_name": team.get("team_name", "N/A"),
                "errors": errors,
            })

    ranked_teams = rank_teams(valid_records)
    print_hackathon_report(ranked_teams, invalid_reports, cross_duplicates)


if __name__ == "__main__":
    main()
