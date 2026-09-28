import { describe, expect, it } from "vitest";
import type { Flyer } from "./domain";
import { flyerState } from "./domain";
import { flyerCountdown, flyerDateRange, flyerStateLabel } from "./flyers";

const flyer = (valid_from: string | null, valid_until: string | null) => ({ valid_from, valid_until }) as unknown as Flyer;
const now = new Date("2026-09-27T12:00:00-03:00");

describe("flyer validity", () => {
  it("a flyer with both dates is current only inside them", () => {
    expect(flyerState(flyer("2026-09-25T00:00:00-03:00", "2026-09-30T23:59:59-03:00"), now)).toBe("current");
    expect(flyerState(flyer("2026-09-01T00:00:00-03:00", "2026-09-10T23:59:59-03:00"), now)).toBe("expired");
  });

  it("a flyer with a start but no end date is still running (its source gives no end)", () => {
    const open = flyer("2026-09-26T00:00:00-03:00", null);
    expect(flyerState(open, now)).toBe("current");
    // Still current, but the wording does not promise a validity the source never stated.
    expect(flyerCountdown(open, now)).toBe("Data final não informada");
    expect(flyerStateLabel(open, now)).toBe("Publicado, sem data final");
    expect(flyerStateLabel(flyer("2026-09-25T00:00:00-03:00", "2026-09-30T23:59:59-03:00"), now)).toBe("Dentro da validade");
    expect(flyerDateRange(open)).toMatch(/^A partir de /);
    expect(flyerState(flyer("2026-10-01T00:00:00-03:00", null), now)).toBe("future");
  });

  it("a flyer with no start date has an unknown validity", () => {
    expect(flyerState(flyer(null, null), now)).toBe("unknown");
    expect(flyerState(flyer(null, "2026-09-30T00:00:00-03:00"), now)).toBe("unknown");
  });
});
