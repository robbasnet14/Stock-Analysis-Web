import express from "express";
import cors from "cors";
import { ZodError } from "zod";
import { config } from "./config.js";
import { marketRouter } from "./routes/marketRoutes.js";
import { refreshMarketSnapshot } from "./services/overviewService.js";

const app = express();

app.use(
  cors({
    origin: config.clientOrigin
  })
);
app.use(express.json());

app.use("/api", marketRouter);

app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  if (error instanceof ZodError) {
    res.status(400).json({ error: "Invalid request", details: error.issues });
    return;
  }

  const message = error instanceof Error ? error.message : "Unexpected server error";
  res.status(500).json({ error: message });
});

async function bootstrap(): Promise<void> {
  await refreshMarketSnapshot();

  setInterval(() => {
    refreshMarketSnapshot().catch((error: unknown) => {
      const message = error instanceof Error ? error.message : "Unknown error";
      console.error("Snapshot refresh failed:", message);
    });
  }, config.pollIntervalMs);

  app.listen(config.port, () => {
    console.log(`Quant API running on http://localhost:${config.port}`);
  });
}

bootstrap().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "Unknown startup error";
  console.error("API bootstrap failed:", message);
  process.exit(1);
});
