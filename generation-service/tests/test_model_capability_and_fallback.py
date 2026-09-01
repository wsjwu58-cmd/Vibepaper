from generation.domain.model_capability import ModelCapability, ModelResolver, ModelUnavailable


def test_capability_rejects_unsupported_parameters_and_preserves_price_cap() -> None:
    primary = ModelCapability(
        model_id="video-v1", provider="primary", input_types=frozenset({"image"}), output_type="video",
        max_duration_seconds=5, resolutions=frozenset({"1080p"}), supports_reference_images=True,
        price_version="p1", price_points=35, fallback_group="video", retry_budget=1,
    )
    fallback = ModelCapability(
        model_id="video-v2", provider="fallback", input_types=frozenset({"image"}), output_type="video",
        max_duration_seconds=5, resolutions=frozenset({"1080p"}), supports_reference_images=True,
        price_version="p2", price_points=35, fallback_group="video", retry_budget=0,
    )
    resolver = ModelResolver([primary, fallback])
    assert resolver.estimate("video-v1", {"duration_seconds": 5, "resolution": "1080p"}) == 35
    try:
        resolver.resolve("video-v1", {"duration_seconds": 6, "resolution": "1080p"})
        raise AssertionError("expected unsupported parameter")
    except ModelUnavailable as error:
        assert error.code == "UNSUPPORTED_PARAMETER"
    selected = resolver.resolve_with_fallback("video-v1", {"duration_seconds": 5, "resolution": "1080p"}, failed_models={"video-v1"}, cost_cap=35)
    assert selected.model_id == "video-v2"


def test_retry_budget_is_exhausted() -> None:
    capability = ModelCapability(
        model_id="video-v1", provider="primary", input_types=frozenset({"text"}), output_type="video",
        max_duration_seconds=5, resolutions=frozenset({"720p"}), supports_reference_images=False,
        price_version="p1", price_points=10, fallback_group="video", retry_budget=0,
    )
    try:
        ModelResolver([capability]).resolve_with_fallback("video-v1", {"duration_seconds": 5, "resolution": "720p"}, failed_models={"video-v1"}, cost_cap=10)
        raise AssertionError("expected retry exhaustion")
    except ModelUnavailable as error:
        assert error.code == "RETRY_BUDGET_EXHAUSTED"
