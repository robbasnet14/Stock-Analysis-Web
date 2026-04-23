import { Router } from "express";
import { z } from "zod";
import { getSnapshot, refreshMarketSnapshot } from "../services/overviewService.js";
import { watchlistStore } from "../data/watchlistStore.js";
import { generateChatReply } from "../services/chatService.js";

const addSchema = z.object({ symbol: z.string().min(1).max(8) });
const removeSchema = z.object({ symbol: z.string().min(1).max(8) });
const chatSchema = z.object({
  messages: z.array(
    z.object({
      role: z.enum(["user", "assistant"]),
      content: z.string().min(1)
    })
  )
});

export const marketRouter = Router();

marketRouter.get("/health", (_req, res) => {
  res.json({ ok: true, service: "quant-api", time: new Date().toISOString() });
});

marketRouter.get("/overview", async (_req, res, next) => {
  try {
    if (getSnapshot().topBullCases.length === 0) {
      await refreshMarketSnapshot();
    }
    res.json(getSnapshot());
  } catch (error) {
    next(error);
  }
});

marketRouter.get("/refresh", async (_req, res, next) => {
  try {
    const snapshot = await refreshMarketSnapshot();
    res.json(snapshot);
  } catch (error) {
    next(error);
  }
});

marketRouter.get("/alerts", (_req, res) => {
  res.json({ alerts: getSnapshot().alerts });
});

marketRouter.get("/watchlist", (_req, res) => {
  res.json({ watchlist: watchlistStore.getAll() });
});

marketRouter.post("/watchlist", async (req, res, next) => {
  try {
    const body = addSchema.parse(req.body);
    const watchlist = watchlistStore.add(body.symbol);
    await refreshMarketSnapshot();
    res.status(201).json({ watchlist });
  } catch (error) {
    next(error);
  }
});

marketRouter.delete("/watchlist", async (req, res, next) => {
  try {
    const body = removeSchema.parse(req.body);
    const watchlist = watchlistStore.remove(body.symbol);
    await refreshMarketSnapshot();
    res.json({ watchlist });
  } catch (error) {
    next(error);
  }
});

marketRouter.post("/chat", async (req, res, next) => {
  try {
    const body = chatSchema.parse(req.body);
    const snapshot = getSnapshot().topBullCases.length ? getSnapshot() : await refreshMarketSnapshot();
    const reply = await generateChatReply(body.messages, snapshot);
    res.json({ reply });
  } catch (error) {
    next(error);
  }
});
