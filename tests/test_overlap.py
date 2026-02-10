from portfolio_analyzer.analysis.overlap import compute_overlap


def test_vti_voo_high_overlap(sample_portfolio):
    pairs = compute_overlap(sample_portfolio)
    vti_voo = next(p for p in pairs if {p.etf_a, p.etf_b} == {"VTI", "VOO"})
    # All 5 holdings shared between VTI and VOO
    assert len(vti_voo.shared_holdings) == 5
    assert vti_voo.overlap_coefficient == 1.0


def test_vxus_no_overlap_with_us(sample_portfolio):
    pairs = compute_overlap(sample_portfolio)
    vxus_pairs = [p for p in pairs if "VXUS" in (p.etf_a, p.etf_b)]
    # VXUS has no shared holdings with VTI or VOO in our fixture data
    assert len(vxus_pairs) == 0


def test_sorted_by_overlap_coefficient(sample_portfolio):
    pairs = compute_overlap(sample_portfolio)
    coeffs = [p.overlap_coefficient for p in pairs]
    assert coeffs == sorted(coeffs, reverse=True)


def test_overlap_weights_positive(sample_portfolio):
    pairs = compute_overlap(sample_portfolio)
    for pair in pairs:
        assert pair.overlap_weight_a > 0
        assert pair.overlap_weight_b > 0
