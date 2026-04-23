import dotenv from "dotenv";

dotenv.config();

export const config = {
  port: Number(process.env.PORT ?? 4000),
  clientOrigin: process.env.CLIENT_ORIGIN ?? "http://localhost:5173",
  pollIntervalMs: Number(process.env.POLL_INTERVAL_MS ?? 60_000),
  finnhubApiKey: process.env.FINNHUB_API_KEY ?? "",
  polygonApiKey: process.env.POLYGON_API_KEY ?? "",
  alphaVantageApiKey: process.env.ALPHAVANTAGE_API_KEY ?? "",
  openAiApiKey: process.env.OPENAI_API_KEY ?? "",
  openAiModel: process.env.OPENAI_MODEL ?? "gpt-4o-mini"
};
