import OpenAI from "openai";
import { ChatMessage, MarketOverview } from "../models/types.js";
import { config } from "../config.js";

const client = config.openAiApiKey ? new OpenAI({ apiKey: config.openAiApiKey }) : null;

export async function generateChatReply(messages: ChatMessage[], snapshot: MarketOverview): Promise<string> {
  const latestUser = messages.filter((m) => m.role === "user").at(-1)?.content ?? "";

  if (!client) {
    return [
      "Live AI mode is disabled because OPENAI_API_KEY is not configured.",
      "",
      `Current top bull case: ${snapshot.topBullCases[0]?.symbol ?? "N/A"} with score ${snapshot.topBullCases[0]?.score ?? "N/A"}.`,
      "",
      `Question received: \"${latestUser}\"`,
      "",
      "To enable AI chat, set OPENAI_API_KEY in apps/api/.env and restart the API."
    ].join("\n");
  }

  const context = {
    generatedAt: snapshot.timestamp,
    topSignals: snapshot.topBullCases.slice(0, 5),
    setups: snapshot.tradeSetups.slice(0, 5),
    alerts: snapshot.alerts.slice(0, 5),
    news: snapshot.news.slice(0, 6).map((n) => ({
      headline: n.headline,
      sentimentScore: n.sentimentScore,
      symbols: n.symbols,
      publishedAt: n.publishedAt
    }))
  };

  const completion = await client.chat.completions.create({
    model: config.openAiModel,
    temperature: 0.2,
    messages: [
      {
        role: "system",
        content:
          "You are a disciplined quant market assistant. Provide concise trade insight with clear entries, stops, targets, and risks. Do not guarantee outcomes."
      },
      {
        role: "system",
        content: `Market snapshot JSON: ${JSON.stringify(context)}`
      },
      ...messages.map((m) => ({ role: m.role, content: m.content }))
    ]
  });

  return completion.choices[0]?.message?.content ?? "No response generated.";
}
