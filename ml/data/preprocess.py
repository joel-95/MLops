import pandas as pd
import numpy as np
from typing import Tuple, List, Dict, Any
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline


class PreprocessorBundle:
    """
    Serialisable wrapper holding the fitted ColumnTransformer and feature metadata.
    """
    def __init__(
        self,
        transformer: ColumnTransformer,
        numerical_features: List[str],
        categorical_features: List[str],
        target_column: str,
        feature_names_out: List[str]
    ):
        self.transformer = transformer
        self.numerical_features = numerical_features
        self.categorical_features = categorical_features
        self.target_column = target_column
        self.feature_names_out = feature_names_out

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        return self.transformer.transform(df)

    def transform_single(self, input_dict: Dict[str, Any]) -> np.ndarray:
        df = pd.DataFrame([input_dict])
        return self.transformer.transform(df)


def preprocess(
    raw_df: pd.DataFrame,
    target_column: str,
    numerical_features: List[str],
    categorical_features: List[str],
    test_size: float = 0.2,
    random_state: int = 42
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, PreprocessorBundle]:
    """
    Reusable data cleaning, encoding, imputation and splitting pipeline.
    
    Returns:
        (X_train, X_test, y_train, y_test, preprocessor_bundle)
    """
    df = raw_df.copy()

    # 1. Clean target column: drop rows missing target
    if target_column not in df.columns:
        raise ValueError(f"Target column '{target_column}' does not exist in dataframe columns: {list(df.columns)}")
    
    df = df.dropna(subset=[target_column])
    y = df[target_column].values

    # 2. Extract feature dataframe
    feature_cols = numerical_features + categorical_features
    missing_cols = [c for c in feature_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Features missing from raw dataset: {missing_cols}")

    X_df = df[feature_cols]

    # 3. Build transformers
    transformers = []

    if numerical_features:
        num_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler())
        ])
        transformers.append(("num", num_pipeline, numerical_features))

    if categorical_features:
        cat_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))
        ])
        transformers.append(("cat", cat_pipeline, categorical_features))

    column_transformer = ColumnTransformer(transformers=transformers, remainder="drop")
    column_transformer.fit(X_df)

    # Compute output feature names
    out_names: List[str] = []
    if numerical_features:
        out_names.extend(numerical_features)
    if categorical_features:
        cat_transformer = column_transformer.named_transformers_.get("cat")
        if cat_transformer and hasattr(cat_transformer.named_steps["onehot"], "get_feature_names_out"):
            out_names.extend(cat_transformer.named_steps["onehot"].get_feature_names_out(categorical_features).tolist())

    bundle = PreprocessorBundle(
        transformer=column_transformer,
        numerical_features=numerical_features,
        categorical_features=categorical_features,
        target_column=target_column,
        feature_names_out=out_names
    )

    X_transformed = column_transformer.transform(X_df)

    # 4. Train / test split
    X_train, X_test, y_train, y_test = train_test_split(
        X_transformed,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y if len(np.unique(y)) > 1 and len(np.unique(y)) < 20 else None
    )

    return X_train, X_test, y_train, y_test, bundle


def apply_preprocessing(raw_input: Dict[str, Any], preprocessor: PreprocessorBundle) -> np.ndarray:
    """
    Applies the saved preprocessor bundle to a single prediction input dictionary.
    """
    return preprocessor.transform_single(raw_input)
