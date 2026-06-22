"""Tests for the Part 3 Protocol-3 multi-RM blind-spot audit (offline parts).

Covers the RewardAdapter registry/metadata and the pure merge aggregation
(verdict, G7 cross-model row, prompt-sensitivity, cross-RM fidelity). No GPU /
no weights — the scoring forward pass is exercised by the live audit scripts.
"""
import importlib.util
from pathlib import Path

from slide_examiner import reward_adapters as RA

REPO = Path(__file__).resolve().parents[1]


def _load_merge():
    spec = importlib.util.spec_from_file_location(
        "p3_merge", REPO / "scripts" / "part3_p3_audit_merge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_registry_has_four_adapters_and_three_categories() -> None:
    assert set(RA.ADAPTERS) == {"docreward", "skywork-vl", "ixc-2.5", "aesthetic"}
    cats = {cls.category for cls in RA.ADAPTERS.values()}
    # document / general_mm / aesthetic span (general_mm shared by skywork+ixc)
    assert {"document", "general_mm", "aesthetic"} <= cats


def test_contracts_and_trained_flags() -> None:
    assert RA.SkyworkVLAdapter.contract == RA.PROMPT_CONDITIONED
    assert RA.IXCRewardAdapter.contract == RA.PROMPT_CONDITIONED
    assert RA.DocRewardAdapter.contract == RA.PAIRWISE_BT
    assert RA.AestheticAdapter.contract == RA.POINTWISE
    # only the aesthetic CLIP head is a non-trained heuristic
    assert RA.AestheticAdapter.trained_reward is False
    for k in ("docreward", "skywork-vl", "ixc-2.5"):
        assert RA.ADAPTERS[k].trained_reward is True


def test_build_returns_unloaded_adapter_with_meta() -> None:
    a = RA.build("skywork-vl", path="/nonexistent")  # load() not called -> no I/O
    m = a.meta()
    assert m["key"] == "skywork-vl" and m["backbone"] == "Qwen2.5-VL-7B"
    assert m["category"] == "general_mm" and m["trained_reward"] is True


def _audit(key, name, category, backbone, trained, g7_pref, g7_ci, g7_gap,
           contract=RA.PROMPT_CONDITIONED, variant="generic"):
    """Minimal per-RM audit dict (generic variant) with a G7 + one sensitive cell."""
    return {
        "key": key, "display_name": name, "category": category, "contract": contract,
        "backbone": backbone, "trained_reward": trained, "model_path": f"/m/{key}",
        "variant": variant, "elicitation": None,
        "results": [
            {"defect": "G7_RENDER_CONTAINMENT_OVERFLOW", "render": "freeform", "n": 40,
             "preference_accuracy": g7_pref, "preference_ci": g7_ci,
             "mean_reward_gap_clean_minus_def": g7_gap, "median_gap": g7_gap,
             "n_clean_preferred": int(round(g7_pref * 40))},
            {"defect": "G2_ELEMENT_OVERLAP", "render": "freeform", "n": 40,
             "preference_accuracy": 1.0, "preference_ci": [0.9, 1.0],
             "mean_reward_gap_clean_minus_def": 2.0, "median_gap": 2.0, "n_clean_preferred": 40},
            {"defect": "G2_ELEMENT_OVERLAP", "render": "template", "n": 40,
             "preference_accuracy": 0.0, "preference_ci": [0.0, 0.09],
             "mean_reward_gap_clean_minus_def": 0.0, "median_gap": 0.0, "n_clean_preferred": 0},
        ],
    }


def test_merge_verdict_all_trained_below_chance() -> None:
    merge = _load_merge()
    primary = {
        "docreward": _audit("docreward", "DocReward-3B", "document", "Qwen2.5-VL-3B", True,
                            0.28, [0.16, 0.43], -0.23, contract=RA.PAIRWISE_BT),
        "skywork-vl": _audit("skywork-vl", "Skywork-VL-Reward-7B", "general_mm",
                             "Qwen2.5-VL-7B", True, 0.45, [0.30, 0.61], -0.05),
        "aesthetic": _audit("aesthetic", "LAION-Aesthetic", "aesthetic", "CLIP ViT-L/14",
                            False, 0.50, [0.35, 0.65], 0.0, contract=RA.POINTWISE),
    }
    audit_multi, fidelity_multi = merge.summarize(primary, {}, pixel_fidelity={
        "overall": {"template_absorption_rate": 0.45},
        "per_defect": {"G2_ELEMENT_OVERLAP": {"template_absorption_rate": 1.0}}})

    assert audit_multi["n_models"] == 3
    assert audit_multi["verdict"]["n_trained_rewards"] == 2
    assert audit_multi["verdict"]["all_trained_rewards_at_or_below_chance_on_g7"] is True
    # G7 row sorted helper present for all 3
    keys = {r["key"] for r in audit_multi["g7_cross_model"]}
    assert keys == {"docreward", "skywork-vl", "aesthetic"}
    # cross-RM fidelity: each model's snap-absorbed G2 has gap 0
    fm = {m["key"]: m for m in fidelity_multi["per_reward_model"]}
    assert fm["docreward"]["template_snap_absorbed"]["G2_ELEMENT_OVERLAP"]["mean_gap"] == 0.0
    assert fidelity_multi["pixel_level_absorption"]["overall_template_absorption_rate"] == 0.45


def test_merge_verdict_fails_if_a_trained_rm_sees_g7() -> None:
    merge = _load_merge()
    primary = {
        "docreward": _audit("docreward", "DocReward-3B", "document", "Qwen2.5-VL-3B", True,
                            0.28, [0.16, 0.43], -0.23, contract=RA.PAIRWISE_BT),
        # a trained RM that DOES see G7 (CI above chance) breaks the verdict
        "skywork-vl": _audit("skywork-vl", "Skywork-VL-Reward-7B", "general_mm",
                             "Qwen2.5-VL-7B", True, 0.95, [0.83, 0.99], 0.6),
    }
    audit_multi, _ = merge.summarize(primary, {})
    assert audit_multi["verdict"]["all_trained_rewards_at_or_below_chance_on_g7"] is False


def test_merge_elicitation_recoverability_pairs_generic_and_probe() -> None:
    merge = _load_merge()
    primary = {"skywork-vl": _audit("skywork-vl", "Skywork-VL-Reward-7B", "general_mm",
                                    "Qwen2.5-VL-7B", True, 0.45, [0.30, 0.61], -0.05)}
    probe = {"skywork-vl": _audit("skywork-vl", "Skywork-VL-Reward-7B", "general_mm",
                                  "Qwen2.5-VL-7B", True, 0.85, [0.70, 0.93], 1.40,
                                  variant="probe")}
    audit_multi, _ = merge.summarize(primary, probe)
    sens = audit_multi["prompt_sensitivity_g7"]
    assert len(sens) == 1
    assert sens[0]["g7_generic_pref"] == 0.45 and sens[0]["g7_probe_pref"] == 0.85
