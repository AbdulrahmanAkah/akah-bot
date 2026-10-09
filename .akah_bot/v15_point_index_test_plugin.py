def pytest_configure(config):
    import cache_budget_v15
    import v15_native_epoch_candidate
    cache_budget_v15.install(); v15_native_epoch_candidate.install()
    import v15_point_query_index
    v15_point_query_index.install()
