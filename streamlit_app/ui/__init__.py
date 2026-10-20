"""ClaimCheck Pro 现代 UI 设计系统与组件包
"""

from streamlit_app.ui.theme import inject_custom_theme
from streamlit_app.ui.components import (
    render_top_navbar,
    render_hero_banner,
    render_status_badge,
    render_budget_pill,
    render_stepper,
    render_metric_cards,
    render_overall_summary_card,
    render_identity_card,
    render_claim_item,
    render_advice_and_disclaimer,
    render_report_actions,
    render_example_drawer,
    render_report_metadata_header,
    render_degradation_action_card,
    render_claim_confirmation_card,
    render_search_execution_panel,
)

__all__ = [
    "inject_custom_theme",
    "render_top_navbar",
    "render_hero_banner",
    "render_status_badge",
    "render_budget_pill",
    "render_stepper",
    "render_metric_cards",
    "render_overall_summary_card",
    "render_identity_card",
    "render_claim_item",
    "render_advice_and_disclaimer",
    "render_report_actions",
    "render_example_drawer",
    "render_report_metadata_header",
    "render_degradation_action_card",
    "render_claim_confirmation_card",
    "render_search_execution_panel",
]

