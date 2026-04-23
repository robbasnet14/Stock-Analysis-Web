from pydantic import BaseModel, Field


class EnsembleModelsOut(BaseModel):
    factor_model: float
    technical_model: float
    sentiment_model: float
    macro_model: float


class EnsembleItemOut(BaseModel):
    symbol: str
    final_score: float
    models: EnsembleModelsOut


class EnsembleContributionOut(BaseModel):
    factor_model: float
    technical_model: float
    sentiment_model: float
    macro_model: float


class EnsembleConfidenceBandOut(BaseModel):
    low: float
    base: float
    high: float


class EnsembleDiagnosticsItemOut(BaseModel):
    symbol: str
    final_score: float
    feature_contribution: EnsembleContributionOut
    confidence: float
    confidence_band: EnsembleConfidenceBandOut
    models: EnsembleModelsOut


class SectorStrengthOut(BaseModel):
    sector: str
    strength: float
    avg_return_5d: float
    avg_return_20d: float
    volume_strength: float


class TrendingItemOut(BaseModel):
    symbol: str
    trending_score: float
    factors: dict[str, float]


class PortfolioOptimizeIn(BaseModel):
    symbols: list[str] = Field(default_factory=list, min_length=2)


class PortfolioOptimizeOut(BaseModel):
    recommended_weights: dict[str, float]
    expected_return: float
    portfolio_volatility: float
    sharpe_ratio: float
