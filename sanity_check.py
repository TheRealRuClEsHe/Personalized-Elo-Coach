try:
    from mgz.fast import header as fast_header, operation, Operation, Action, meta
    import pandas as pd
    import numpy as np
    import xgboost
    import shap
    import sklearn
    import fastapi
    import jinja2
    print("All imports OK — environment is ready.")
except ImportError as e:
    print(f"FAILED: {e}")
    print("Fix this import error before starting Week 1.")
