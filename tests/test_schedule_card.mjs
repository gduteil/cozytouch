/*
 * What the schedule card does to a day when somebody edits its slots.
 *
 * Run by hand -- `node --test tests/test_schedule_card.mjs` -- since CI has
 * no javascript job. The rest of the suite is python.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  nowInWeek,
  addSlot,
  inChargeAt,
  writeSlot,
} from "../custom_components/cozytouch/www/cozytouch-schedule-card.js";

const DAY = [
  { time: "00:00", temperature: 17 },
  { time: "07:30", temperature: 21 },
  { time: "22:00", temperature: 17 },
];

test("a setpoint holds until the next slot takes over", () => {
  assert.equal(inChargeAt(DAY, 0), 17);
  assert.equal(inChargeAt(DAY, 7 * 60), 17);
  assert.equal(inChargeAt(DAY, 7 * 60 + 30), 21);
  assert.equal(inChargeAt(DAY, 23 * 60), 17);
});

test("nothing is in charge before the first slot", () => {
  assert.equal(inChargeAt([{ time: "06:00", temperature: 19 }], 0), null);
});

test("a slot keeps its temperature when it is moved", () => {
  assert.deepEqual(writeSlot(DAY, 1, { time: "06:15" }), [
    { time: "00:00", temperature: 17 },
    { time: "06:15", temperature: 21 },
    { time: "22:00", temperature: 17 },
  ]);
});

test("moving a slot past the next one re-sorts the day", () => {
  assert.deepEqual(writeSlot(DAY, 1, { time: "23:00" }), [
    { time: "00:00", temperature: 17 },
    { time: "22:00", temperature: 17 },
    { time: "23:00", temperature: 21 },
  ]);
});

test("a slot keeps its time when its setpoint changes", () => {
  assert.deepEqual(writeSlot(DAY, 2, { temperature: 18.5 })[2], {
    time: "22:00",
    temperature: 18.5,
  });
});

test("dropping a slot leaves the rest alone", () => {
  assert.deepEqual(writeSlot(DAY, 1, null), [
    { time: "00:00", temperature: 17 },
    { time: "22:00", temperature: 17 },
  ]);
});

test("the day must keep a slot at 00:00", () => {
  assert.throws(() => writeSlot(DAY, 0, null), { code: "midnight" });
  assert.throws(() => writeSlot(DAY, 0, { time: "01:00" }), { code: "midnight" });
});

test("00:00 can still be given another setpoint", () => {
  assert.equal(writeSlot(DAY, 0, { temperature: 16 })[0].temperature, 16);
});

test("two slots cannot start at the same time", () => {
  assert.throws(() => writeSlot(DAY, 2, { time: "07:30" }), {
    code: "duplicate",
  });
});

test("a new slot lands mid-way through the longest empty stretch", () => {
  // 07:30 to 22:00 is the widest gap ; its middle is 14:45, rounded to the
  // half hour, and it holds what was already in charge there.
  assert.deepEqual(addSlot(DAY)[2], { time: "15:00", temperature: 21 });
});

test("a new slot after the last one still lands inside the day", () => {
  const evening = [{ time: "00:00", temperature: 19 }];
  const [, added] = addSlot(evening);
  assert.equal(added.time, "12:00");
  assert.equal(added.temperature, 19);
});

test("a day refuses an eleventh slot", () => {
  const full = Array.from({ length: 10 }, (_, index) => ({
    time: `${String(index * 2).padStart(2, "0")}:00`,
    temperature: 20,
  }));
  assert.throws(() => addSlot(full), { code: "full" });
});

test("editing leaves the original untouched", () => {
  const before = JSON.stringify(DAY);
  writeSlot(DAY, 1, { time: "09:00" });
  addSlot(DAY);
  assert.equal(JSON.stringify(DAY), before);
});

test("the week's now is a Monday-first day and a minute of it", () => {
  // A Sunday, since that is the index getDay() puts first and DAYS last.
  assert.deepEqual(nowInWeek(new Date(2026, 8, 13, 7, 5)), {
    day: "sunday",
    minute: 425,
  });
  assert.equal(nowInWeek(new Date(2026, 8, 14, 0, 0)).day, "monday");
});

test("the setpoint in charge is the last slot before the minute", () => {
  assert.equal(inChargeAt(DAY, nowInWeek(new Date(2026, 8, 14, 0, 30)).minute),
    DAY[0].temperature);
});
