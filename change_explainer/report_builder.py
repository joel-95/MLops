from typing import List, Dict, Any, Optional


def build_change_report(
    code_findings: List[str],
    comparator_report: Dict[str, Any],
    old_metrics: Optional[Dict[str, Any]],
    new_metrics: Optional[Dict[str, Any]],
    use_llm: bool = False
) -> Dict[str, Any]:
    """
    Combines AST code diff findings, metric deltas, and data drift findings
    into a human-readable explanation of 'Why model performance changed'.

    Returns:
        Structured change explanation dict.
    """
    old_metrics = old_metrics or {}
    new_metrics = new_metrics or {}

    # 1. Compute Metric Deltas
    metric_deltas: Dict[str, Any] = {}
    metric_bullet_points: List[str] = []

    all_metrics = set(old_metrics.keys()).union(new_metrics.keys())
    for m in sorted(list(all_metrics)):
        if m in ["timestamp", "commit_sha", "task_type", "model_artifact_path"]:
            continue
        v_old = old_metrics.get(m)
        v_new = new_metrics.get(m)
        if isinstance(v_old, (int, float)) and isinstance(v_new, (int, float)):
            delta = round(float(v_new - v_old), 4)
            pct = round((delta / v_old) * 100, 2) if v_old != 0 else 0.0
            sign = "+" if delta > 0 else ""
            metric_deltas[m] = {
                "old": v_old,
                "new": v_new,
                "delta": delta,
                "percent_change": pct
            }
            metric_bullet_points.append(
                f"Metric '{m}': {v_old} → {v_new} ({sign}{delta}, {sign}{pct}%)"
            )

    # 2. Extract Drift Summary
    drift_detected = comparator_report.get("dataset_drift", False)
    drifted_features = comparator_report.get("drifted_features", [])
    if drift_detected:
        drift_note = f"Data drift detected in features: {', '.join(drifted_features)}"
    else:
        drift_note = "No significant dataset drift detected between versions."

    # 3. Build Detailed Findings List
    details: List[str] = []
    details.extend([f"Code: {cf}" for cf in code_findings])
    details.extend([f"Performance: {mb}" for mb in metric_bullet_points])
    details.append(f"Drift Analysis: {drift_note}")

    # 4. Generate Narrative Summary
    code_summary = code_findings[0] if code_findings else "No script changes."
    primary_metric_msg = ""
    for target_m in ["accuracy", "f1", "rmse", "r_squared"]:
        if target_m in metric_deltas:
            d = metric_deltas[target_m]
            sign = "+" if d["delta"] > 0 else ""
            primary_metric_msg = f"{target_m} shifted by {sign}{d['delta']} ({d['old']} → {d['new']})."
            break

    summary = f"{code_summary} {primary_metric_msg} {drift_note}".strip()

    return {
        "summary": summary,
        "details": details,
        "code_changes": code_findings,
        "metric_deltas": metric_deltas,
        "drift_summary": {
            "drift_detected": drift_detected,
            "drifted_features": drifted_features
        }
    }
