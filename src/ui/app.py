"""Streamlit Presentation Layer (architecture §9, Phase P4)."""

import os
import re
import sys
import logging
import httpx
import streamlit as st

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add workspace root to sys.path to allow local fallback imports
from pathlib import Path
workspace_root = str(Path(__file__).resolve().parent.parent.parent)
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

# Remove any pre-imported 'src' packages from sys.modules to prevent namespace collision with Streamlit's /mount/src path
for key in list(sys.modules.keys()):
    if key == "src" or key.startswith("src."):
        sys.modules.pop(key, None)

IMPORT_ERROR = None
# Try imports for local fallback
try:
    from src.config import get_settings
    from src.data.ingestion import load_and_index
    from src.data.index import get_index
    from src.services.recommender import RecommendationOrchestrator
    from src.data.models import UserPreferences, CostBand

    LOCAL_BACKEND_AVAILABLE = True
except Exception as e:
    logger.exception("Failed to import local backend components: %s", e)
    IMPORT_ERROR = e
    LOCAL_BACKEND_AVAILABLE = False

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def is_api_server_active() -> bool:
    """Check if the FastAPI backend is running and healthy."""
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False


# Page configuration
st.set_page_config(
    page_title="GASTRO-AI | Premium Recommender",
    page_icon="🍽️",
    layout="wide",
)

# Custom premium styling using CSS (Outfit font, Lumina Gastronomy design system)
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@100..900&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap');

    /* Global Typography and Colors - Lumina Gastronomy Palette */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        font-family: 'Outfit', sans-serif !important;
        background-color: #1e0f10 !important;
        color: #f9dcdc !important;
    }

    /* Sidebar background override */
    [data-testid="stSidebar"] {
        background-color: rgba(43, 27, 28, 0.75) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
        backdrop-filter: blur(12px) !important;
    }

    /* Custom Gradient Header */
    .main-title {
        font-weight: 700;
        font-size: 2.8rem;
        background: linear-gradient(135deg, #ffb2b7 0%, #ff516a 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
        text-shadow: 0px 4px 12px rgba(255, 81, 106, 0.2);
    }

    .sub-title {
        font-weight: 300;
        font-size: 1.15rem;
        color: #e3bdbf;
        margin-bottom: 2rem;
    }

    /* Premium Glassmorphic Cards */
    .restaurant-card {
        background: rgba(30, 41, 59, 0.7) !important;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.25);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .restaurant-card:hover {
        transform: translateY(-4px);
        border-color: rgba(255, 178, 183, 0.3);
        box-shadow: 0 12px 40px 0 rgba(255, 81, 106, 0.15);
    }

    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        flex-wrap: wrap;
        gap: 8px;
    }

    .restaurant-name {
        font-size: 1.45rem;
        font-weight: 600;
        color: #f9dcdc;
        margin: 0;
    }

    .rank-badge {
        background: #ff516a;
        color: #5b0017;
        font-weight: 700;
        font-size: 0.8rem;
        padding: 4px 12px;
        border-radius: 9999px;
        box-shadow: 0 0 20px rgba(255, 81, 106, 0.15);
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .rating-badge {
        background: rgba(238, 194, 0, 0.1) !important;
        border: 1px solid rgba(238, 194, 0, 0.3) !important;
        color: #eec200 !important;
        font-weight: 600;
        font-size: 0.85rem;
        padding: 3px 8px;
        border-radius: 8px;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }

    .details-row {
        display: flex;
        gap: 16px;
        margin-bottom: 16px;
        font-size: 0.9rem;
        color: #e3bdbf;
        flex-wrap: wrap;
    }

    .detail-item {
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .cost-badge {
        background: rgba(164, 201, 255, 0.15) !important;
        border: 1px solid rgba(164, 201, 255, 0.3) !important;
        color: #a4c9ff !important;
        font-weight: 500;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        text-transform: uppercase;
    }

    .explanation-box {
        background: rgba(66, 48, 49, 0.4);
        border-left: 3px solid #ff516a;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        font-size: 0.95rem;
        line-height: 1.5;
        color: #e3bdbf;
    }

    /* AI Summary Container styling */
    .summary-container {
        background: linear-gradient(135deg, rgba(255, 81, 106, 0.08) 0%, rgba(43, 27, 28, 0.25) 100%);
        border: 1px solid rgba(255, 81, 106, 0.18);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 28px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
    }

    .summary-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: #ffb2b7;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .summary-text {
        font-size: 0.975rem;
        line-height: 1.6;
        color: #f9dcdc;
        font-style: italic;
        margin: 0;
    }

    /* Custom Alert Banners */
    .custom-degraded-alert {
        background: rgba(238, 194, 0, 0.08) !important;
        border: 1px solid rgba(238, 194, 0, 0.25) !important;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 24px;
        color: #eec200 !important;
        font-size: 0.9rem;
        line-height: 1.4;
    }

    .mode-badge-api {
        background-color: rgba(238, 194, 0, 0.15) !important;
        border: 1px solid rgba(238, 194, 0, 0.3) !important;
        color: #eec200 !important;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 500;
        letter-spacing: 0.5px;
    }

    .mode-badge-local {
        background-color: rgba(164, 201, 255, 0.15) !important;
        border: 1px solid rgba(164, 201, 255, 0.3) !important;
        color: #a4c9ff !important;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 500;
        letter-spacing: 0.5px;
    }

    .text-label-sm {
        font-size: 12px;
        line-height: 16px;
        letter-spacing: 0.05em;
        font-weight: 600;
    }

    .text-on-surface-variant {
        color: #e3bdbf;
    }

    /* Streamlit controls styled matching design */
    div.stButton > button {
        background: linear-gradient(90deg, #ff516a 0%, #bc0b3b 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 12px !important;
        box-shadow: 0 0 20px rgba(255, 81, 106, 0.2) !important;
        transition: all 0.3s !important;
    }
    div.stButton > button:hover {
        transform: scale(1.02) !important;
        box-shadow: 0 0 25px rgba(255, 81, 106, 0.35) !important;
    }
</style>

""",
    unsafe_allow_html=True,
)

# ----------------- Mode Selection & Liveness -----------------
api_active = is_api_server_active()

if not api_active and not LOCAL_BACKEND_AVAILABLE:
    st.error(
        "Fatal Error: Both the FastAPI server is unreachable and the local packages cannot be imported. Please verify that the virtual environment is fully initialized."
    )
    if IMPORT_ERROR:
        st.exception(IMPORT_ERROR)
    st.stop()

# ----------------- Load Autocomplete Lists -----------------
locations = []
cuisines = []

if api_active:
    try:
        loc_res = httpx.get(f"{API_BASE_URL}/metadata/locations")
        locations = loc_res.json()
        cui_res = httpx.get(f"{API_BASE_URL}/metadata/cuisines")
        cuisines = cui_res.json()
    except Exception as e:
        logger.error("API active but metadata load failed: %s. Falling back to local index.", e)
        api_active = False

if not api_active:
    # Run direct load_and_index local logic
    try:
        try:
            index = get_index()
        except RuntimeError:
            with st.spinner("Initializing and loading local restaurant database..."):
                index, _ = load_and_index()
        locations = index.locations()
        cuisines = index.cuisines()
    except Exception as e:
        st.error(f"Failed to bootstrap local database: {e}")
        st.stop()

# Format cuisines option list
cuisines_opts = ["All Cuisines"] + sorted(cuisines)
locations_opts = sorted(locations)

# ----------------- Main Layout UI -----------------
st.markdown(
    '<div class="main-title">🍽️ GASTRO-AI Restaurant Concierge</div>', unsafe_allow_html=True
)

# Subtitle and integration badges
mode_badge_html = (
    '<span class="mode-badge-api">CONNECTED TO API</span>'
    if api_active
    else '<span class="mode-badge-local">OFFLINE MODE</span>'
)
st.markdown(
    f'<div class="sub-title">Premium AI recommendation engine using structured filters and semantic LLM ranking. &nbsp;&nbsp; {mode_badge_html}</div>',
    unsafe_allow_html=True,
)

# ----------------- Sidebar Inputs -----------------
st.sidebar.markdown("### 🔍 Recommendation Preferences")

selected_location = st.sidebar.selectbox(
    "1. Location (City/Locality)",
    options=locations_opts,
    index=0 if locations_opts else None,
)

selected_budget_label = st.sidebar.selectbox(
    "2. Budget Range",
    options=["Low Budget", "Medium Budget", "High Budget"],
    index=1,
)
# Map to internal values
budget_map = {"Low Budget": "low", "Medium Budget": "medium", "High Budget": "high"}
selected_budget = budget_map[selected_budget_label]

selected_cuisine = st.sidebar.selectbox(
    "3. Cuisine Preference",
    options=cuisines_opts,
    index=0,
)
cuisine_val = "" if selected_cuisine == "All Cuisines" else selected_cuisine

min_rating = st.sidebar.slider(
    "4. Minimum Rating Star",
    min_value=0.0,
    max_value=5.0,
    value=3.5,
    step=0.1,
)

top_k = st.sidebar.slider(
    "5. Max Recommendations to Show",
    min_value=1,
    max_value=15,
    value=5,
    step=1,
)

additional_prefs = st.sidebar.text_area(
    "6. Special Needs / Vibes",
    placeholder="e.g. outdoor seating, family-friendly, quick service, romantic ambiance...",
)

submit_btn = st.sidebar.button(
    "Generate Recommendations",
    use_container_width=True,
    type="primary",
)

# ----------------- Trigger recommendation pipeline -----------------
if submit_btn:
    if not selected_location:
        st.warning("Please select a location.")
        st.stop()

    recommendations_data = []
    summary_text = None
    degraded = False
    filters_applied = {}
    candidates_considered = 0
    message = None

    with st.spinner("AI is analyzing, filtering and ranking restaurants for you..."):
        try:
            if api_active:
                payload = {
                    "location": selected_location,
                    "budget": selected_budget,
                    "cuisine": cuisine_val,
                    "min_rating": min_rating,
                    "additional_preferences": additional_prefs if additional_prefs.strip() else None,
                    "top_k": top_k,
                }

                res = httpx.post(f"{API_BASE_URL}/recommend", json=payload, timeout=30.0)
                if res.status_code == 200:
                    res_data = res.json()
                    recommendations_data = res_data.get("recommendations", [])
                    summary_text = res_data.get("summary")
                    degraded = res_data.get("degraded_mode", False)
                    filters_applied = res_data.get("meta", {}).get("filters_applied", {})
                    candidates_considered = res_data.get("meta", {}).get(
                        "candidates_considered", 0
                    )
                    message = res_data.get("message")
                else:
                    st.error(f"API server error: {res.text}")
                    st.stop()
            else:
                # Standalone mode: call local orchestrator
                from src.data.models import UserPreferences, CostBand

                prefs = UserPreferences(
                    location=selected_location,
                    budget=CostBand(selected_budget),
                    cuisine=cuisine_val,
                    min_rating=min_rating,
                    additional_preferences=additional_prefs if additional_prefs.strip() else None,
                )
                orchestrator = RecommendationOrchestrator()
                response = orchestrator.recommend(prefs, top_k=top_k)

                recommendations_data = [
                    {
                        "rank": rec.rank,
                        "name": rec.restaurant.name,
                        "cuisine": ", ".join(rec.restaurant.cuisines),
                        "rating": rec.restaurant.rating,
                        "estimated_cost": rec.restaurant.cost,
                        "explanation": rec.explanation,
                    }
                    for rec in response.recommendations
                ]
                summary_text = response.summary
                degraded = response.degraded_mode
                filters_applied = response.filters_applied
                candidates_considered = response.candidates_considered
                message = response.message

        except Exception as e:
            st.error(f"Recommendation pipeline failed: {e}")
            logger.exception("Submit click exception: %s", e)
            st.stop()

    # ----------------- Displaying Results -----------------
    # 1. Handle Degraded Mode Banner
    if degraded:
        degraded_msg = (
            message
            if message
            else "The AI explanation engine is currently offline. Showing fallback matches."
        )
        st.markdown(
            f"""
        <div class="custom-degraded-alert">
            <strong>⚠️ DEGRADED PERFORMANCE MODE ACTIVE</strong><br/>
            {degraded_msg}
        </div>
        """,
            unsafe_allow_html=True,
        )

    # 2. Informational Banner (e.g. relaxation messages)
    elif message:
        st.info(message)

    # 3. Empty list handler
    if not recommendations_data:
        st.markdown(
            f"""
        <div class="restaurant-card" style="text-align: center; border-color: rgba(255,255,255,0.05);">
            <div style="font-size: 2.5rem; margin-bottom: 12px;">🔍</div>
            <h4 style="margin: 0 0 8px 0; color: #E2E8F0;">No restaurants match your filters</h4>
            <p style="color: #94A3B8; margin: 0; font-size: 0.95rem;">Try lowering the minimum rating or selecting a different budget band.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.stop()

    # 4. Display AI Summary Block
    if summary_text:
        st.markdown(
            f"""
        <div class="summary-container">
            <div class="summary-title">
                ✨ AI Recommendation Overview
            </div>
            <p class="summary-text">"{summary_text}"</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # 5. Display Cards for Recommendations
    st.markdown(
        f"**Found {len(recommendations_data)} matches** (Considered {candidates_considered} total candidates after filters):"
    )
    st.write("")

    for rec in recommendations_data:
        cost_val = rec.get("estimated_cost", 0.0)
        
        cuisines_list = [c.strip() for c in rec['cuisine'].split(",") if c.strip()]
        cuisine_badges = "".join([f'<span class="px-3 py-1 bg-surface-container-high border border-outline-variant/30 rounded-full text-label-sm text-on-surface-variant mr-1 mb-1 inline-block" style="background: rgba(55, 38, 38, 0.4); border: 1px solid rgba(91, 64, 65, 0.2); border-radius: 9999px; font-size: 0.75rem; color: #e3bdbf; padding: 4px 12px; display: inline-block;">{c}</span>' for c in cuisines_list])

        card_html = f"""
        <div class="restaurant-card">
            <div class="card-header">
                <span class="rank-badge">RANK #{rec['rank']}</span>
                <div class="rating-badge">
                    <span class="material-symbols-outlined text-sm" style="font-variation-settings: 'FILL' 1; font-size: 14px; vertical-align: middle;">star</span>
                    <span style="vertical-align: middle;">{rec['rating']:.1f}</span>
                </div>
            </div>
            <div class="flex justify-between items-start mb-2" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; margin-top: 8px;">
                <h3 class="restaurant-name" style="font-size: 1.45rem; font-weight: 600; color: #f9dcdc; margin: 0;">{rec['name']}</h3>
                <span class="text-on-surface-variant font-label-md" style="font-size: 0.95rem; color: #e3bdbf; line-height: 1.5;">₹{cost_val:.0f} for two</span>
            </div>
            <div class="flex flex-wrap gap-2 mb-4" style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;">
                {cuisine_badges}
            </div>
            <div class="mt-auto p-4 bg-surface-container-high/40 backdrop-blur-sm rounded-xl border border-outline-variant/20" style="background: rgba(55, 38, 38, 0.4); border: 1px solid rgba(91, 64, 65, 0.2); border-radius: 12px; padding: 16px;">
                <div class="flex items-center gap-2 mb-2 text-primary" style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: #ffb2b7;">
                    <span class="material-symbols-outlined text-base" style="font-size: 16px; vertical-align: middle;">auto_awesome</span>
                    <span class="text-label-sm uppercase tracking-wider" style="font-size: 0.75rem; letter-spacing: 0.05em; font-weight: 600; vertical-align: middle;">AI Rationale</span>
                </div>
                <p class="text-body-md text-on-surface-variant italic leading-snug" style="font-size: 0.95rem; color: #e3bdbf; font-style: italic; margin: 0; line-height: 1.4;">
                    {rec['explanation']}
                </p>
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
else:
    # Initial state screen
    st.markdown(
        """
    <div class="restaurant-card text-center relative overflow-hidden group hover:shadow-2xl hover:shadow-primary/5 transition-all duration-700" style="padding: 48px; border-radius: 40px; text-align: center; background: rgba(30, 41, 59, 0.7); position: relative; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.08);">
        <div class="absolute top-10 left-10 opacity-20 animate-bounce" style="animation-duration: 4s; position: absolute; top: 40px; left: 40px; opacity: 0.2;">
            <span class="material-symbols-outlined text-6xl text-primary" style="font-size: 3.5rem; color: #ffb2b7;">local_pizza</span>
        </div>
        <div class="absolute bottom-20 left-20 opacity-20 animate-bounce" style="animation-duration: 5s; position: absolute; bottom: 80px; left: 80px; opacity: 0.2;">
            <span class="material-symbols-outlined text-6xl text-secondary" style="font-size: 3.5rem; color: #a4c9ff;">japanese_curry</span>
        </div>
        <div class="relative z-10 space-y-8">
            <div class="inline-flex p-6 rounded-full bg-white/5 backdrop-blur-xl border border-white/10 mb-4 transition-transform duration-500" style="display: inline-flex; padding: 24px; border-radius: 9999px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); margin-bottom: 16px;">
                <span class="material-symbols-outlined text-6xl text-primary" style="font-size: 3.5rem; color: #ffb2b7;" style="font-variation-settings: 'FILL' 1;">restaurant</span>
            </div>
            <h1 class="font-display-lg text-on-background leading-tight" style="font-size: 2.8rem; font-weight: 700; color: #f9dcdc; line-height: 1.2;">
                Ready for your next <br/>
                <span class="text-transparent bg-clip-text bg-gradient-to-r from-primary to-secondary" style="background: linear-gradient(135deg, #ffb2b7 0%, #ff516a 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">culinary adventure?</span>
            </h1>
            <p class="font-body-lg text-on-surface-variant max-w-2xl mx-auto opacity-80 leading-relaxed" style="font-size: 1.1rem; color: #e3bdbf; max-width: 42rem; margin: 24px auto 0 auto; opacity: 0.8; line-height: 1.6;">
                Our neural network analyzes millions of dining signals to find your perfect match. 
                Adjust the filters on the left and let our AI curate the perfect dining experience for you.
            </p>
            <div class="flex flex-wrap justify-center gap-4 pt-8" style="display: flex; flex-wrap: wrap; justify-content: center; gap: 16px; margin-top: 32px;">
                <div class="px-6 py-3 glass-panel rounded-full flex items-center gap-3" style="padding: 12px 24px; border-radius: 9999px; display: flex; align-items: center; gap: 12px; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.08);">
                    <span class="material-symbols-outlined text-tertiary" style="color: #eec200;">bolt</span>
                    <span class="font-label-md" style="font-weight: 500; font-size: 0.9rem;">Real-time Zomato Sync</span>
                </div>
                <div class="px-6 py-3 glass-panel rounded-full flex items-center gap-3" style="padding: 12px 24px; border-radius: 9999px; display: flex; align-items: center; gap: 12px; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.08);">
                    <span class="material-symbols-outlined text-secondary" style="color: #a4c9ff;">psychology</span>
                    <span class="font-label-md" style="font-weight: 500; font-size: 0.9rem;">Personalized Preference Map</span>
                </div>
                <div class="px-6 py-3 glass-panel rounded-full flex items-center gap-3" style="padding: 12px 24px; border-radius: 9999px; display: flex; align-items: center; gap: 12px; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.08);">
                    <span class="material-symbols-outlined text-primary" style="color: #ffb2b7;">favorite</span>
                    <span class="font-label-md" style="font-weight: 500; font-size: 0.9rem;">98.4% Match Accuracy</span>
                </div>
            </div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
