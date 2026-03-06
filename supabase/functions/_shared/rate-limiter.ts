/**
 * Token-bucket rate limiter for external API calls.
 * Prevents hitting API rate limits in edge functions.
 */

export class RateLimiter {
  private tokens: number;
  private lastRefill: number;
  private readonly maxTokens: number;
  private readonly refillMs: number;

  constructor(tokensPerWindow: number, windowMs: number) {
    this.maxTokens = tokensPerWindow;
    this.tokens = tokensPerWindow;
    this.refillMs = windowMs;
    this.lastRefill = Date.now();
  }

  /** Wait until a token is available, then consume it. */
  async acquire(): Promise<void> {
    this.refill();
    if (this.tokens > 0) {
      this.tokens--;
      return;
    }
    const waitMs = this.refillMs - (Date.now() - this.lastRefill) + 100;
    await new Promise((r) => setTimeout(r, waitMs));
    this.refill();
    this.tokens--;
  }

  private refill(): void {
    const elapsed = Date.now() - this.lastRefill;
    if (elapsed >= this.refillMs) {
      this.tokens = this.maxTokens;
      this.lastRefill = Date.now();
    }
  }
}

/** HubSpot: 100 requests per 10 seconds. Stay under at 90. */
export const hubspotLimiter = new RateLimiter(90, 10_000);

/** Monday.com: 60 requests per minute. Stay under at 50. */
export const mondayLimiter = new RateLimiter(50, 60_000);
