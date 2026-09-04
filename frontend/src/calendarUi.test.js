import test from "node:test";
import assert from "node:assert/strict";
import { nextRoundIndex } from "./calendarUi.js";

const races = [
  {
    round: 17,
    country: "Italy",
    date: "2026-09-06",
    weekend_start: "2026-09-04",
    weekend_end: "2026-09-06",
  },
  {
    round: 18,
    country: "Spain",
    date: "2026-09-14",
    weekend_start: "2026-09-11",
    weekend_end: "2026-09-14",
  },
];

test("keeps Italy on race weekend before the main race", () => {
  assert.equal(nextRoundIndex(races, new Date("2026-09-05T12:00:00")), 0);
});

test("keeps Italy on main race day", () => {
  assert.equal(nextRoundIndex(races, new Date("2026-09-06T20:00:00")), 0);
});

test("switches to Spain the day after Italy's race", () => {
  assert.equal(nextRoundIndex(races, new Date("2026-09-07T09:00:00")), 1);
});
