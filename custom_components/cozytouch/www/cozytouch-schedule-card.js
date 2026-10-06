/*
 * Cozytouch schedule card : a device's own weekly program, edited as the list
 * of slots the device actually stores and written back through
 * cozytouch.set_schedule.
 *
 * The program lives in the device, not in Home Assistant, so what this draws
 * is what runs when Home Assistant is off.
 */

const DAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

// The device stores ten slots a day, unused ones being [0,0]. Mirrors
// MAX_SLOTS in services.py; the service refuses anything longer anyway.
const MAX_SLOTS = 10;

/* The day names are the browser's, in Home Assistant's language :
 * `hass.language` is what the user picked in their profile, and Intl already
 * knows how every locale abbreviates a weekday. The times need no help at
 * all -- an <input type="time"> displays and parses in the browser's own
 * format while its value stays "HH:MM".
 *
 * The handful of words that are not a date live in STRINGS, in the five
 * languages the integration itself ships. They are here rather than in
 * translations/ because a dashboard card cannot read an integration's
 * translation files -- Home Assistant does not serve them to the frontend.
 */
const dayNames = (language) => {
  const format = new Intl.DateTimeFormat(language, {
    weekday: "short",
    timeZone: "UTC",
  });
  // 2024-01-01 was a Monday, so day n of that week is DAYS[n - 1].
  return Object.fromEntries(
    DAYS.map((day, index) => [day, format.format(Date.UTC(2024, 0, index + 1))])
  );
};

const STRINGS = {
  en: { save: "Save", reload: "Reload", loading: "Loading…",
        writing: "Writing…", written: "Written to the device",
        add: "Add a slot", remove: "Remove this slot",
        midnight: "A day has to start at 00:00",
        duplicate: "Two slots cannot start at the same time",
        full: "A day holds %s slots at most" },
  fr: { save: "Enregistrer", reload: "Recharger", loading: "Chargement…",
        writing: "Écriture…", written: "Écrit dans l'appareil",
        add: "Ajouter un créneau", remove: "Supprimer ce créneau",
        midnight: "Une journée doit commencer à 00:00",
        duplicate: "Deux créneaux ne peuvent pas commencer à la même heure",
        full: "Un jour ne tient que %s créneaux" },
  es: { save: "Guardar", reload: "Recargar", loading: "Cargando…",
        writing: "Escribiendo…", written: "Escrito en el dispositivo",
        add: "Añadir una franja", remove: "Eliminar esta franja",
        midnight: "El día tiene que empezar a las 00:00",
        duplicate: "Dos franjas no pueden empezar a la misma hora",
        full: "Un día admite %s franjas como máximo" },
  de: { save: "Speichern", reload: "Neu laden", loading: "Wird geladen…",
        writing: "Wird geschrieben…", written: "Auf das Gerät geschrieben",
        add: "Zeitfenster hinzufügen", remove: "Dieses Zeitfenster entfernen",
        midnight: "Ein Tag muss um 00:00 beginnen",
        duplicate: "Zwei Zeitfenster können nicht gleichzeitig beginnen",
        full: "Ein Tag fasst höchstens %s Zeitfenster" },
  it: { save: "Salva", reload: "Ricarica", loading: "Caricamento…",
        writing: "Scrittura…", written: "Scritto sul dispositivo",
        add: "Aggiungi una fascia", remove: "Rimuovi questa fascia",
        midnight: "Una giornata deve iniziare alle 00:00",
        duplicate: "Due fasce non possono iniziare alla stessa ora",
        full: "Un giorno tiene al massimo %s fasce" },
};

const STYLE = `
  :host {
    /* Mushroom's own token where a mushroom theme defines it, Home
     * Assistant's own where it does not, so the card is as round as whatever
     * it is sitting between. */
    --radius: var(--mush-border-radius, var(--ha-card-border-radius, 12px));
    /* A chip is small enough that the card's own radius would swallow it, so
     * it takes a fraction of it : the default theme lands back on the 8px
     * these were written at, and a rounder theme rounds them too. */
    --chip-radius: calc(var(--radius) * .7);
    --chip-height: 32px;
    --fill: rgba(var(--rgb-primary-text-color, 0, 0, 0), .08);
  }
  ha-card { padding: 16px; border-radius: var(--radius); }
  h2 { font-size: 15px; font-weight: 600; letter-spacing: .01em;
       margin: 0; text-transform: capitalize;
       color: var(--primary-text-color); }

  /* The head is what the card says when it is closed : what the program is
   * asking for right now. The week is the editor behind it. */
  .head { display: flex; align-items: center; gap: 10px; cursor: pointer;
          user-select: none; }
  .head h2 { flex: 1; }
  .now { display: flex; align-items: center; gap: 6px; height: var(--chip-height);
         border-radius: var(--chip-radius); padding: 0 9px; color: rgba(0, 0, 0, .78);
         font-size: 12px; font-weight: 700; }
  .now .at { font-weight: 500; opacity: .75; }
  .caret { color: var(--secondary-text-color); font-size: 11px; width: 10px; }
  .week { margin-top: 14px; }

  /* The day name owns a column of its own : a day with more slots than the
   * card is wide wraps under its own chips, and a wrapped line that started
   * under the name would read as another day. */
  .day { display: grid; grid-template-columns: 34px 1fr; gap: 6px;
         align-items: start; margin-bottom: 6px; }
  .name { font-size: 12px; font-weight: 500; line-height: var(--chip-height);
          color: var(--secondary-text-color); }
  .slots { display: flex; flex-wrap: wrap; gap: 6px; }

  /* A slot is one chip carrying the two things it is : when it starts and
   * what it asks for. The inputs are native, so the time picker and the
   * number keyboard are the ones the phone already has. */
  .slot { display: flex; align-items: center; height: var(--chip-height);
          border-radius: var(--chip-radius); padding: 0 2px 0 7px; color: rgba(0, 0, 0, .78);
          font-size: 12px; font-weight: 600; }
  .slot input { appearance: none; border: none; background: transparent;
                font: inherit; color: inherit; padding: 0; }
  .slot input[type=time] { width: 44px; min-width: 0; font-weight: 700;
                           opacity: .8; }
  .slot input[type=time]::-webkit-calendar-picker-indicator { display: none; }
  .slot input[type=number] { width: 24px; min-width: 0; text-align: right;
                             margin-left: 6px; -moz-appearance: textfield; }
  .slot input[type=number]::-webkit-inner-spin-button,
  .slot input[type=number]::-webkit-outer-spin-button { appearance: none; }
  .slot .unit { padding-right: 2px; }
  .slot button { border: none; background: transparent; cursor: pointer;
                 color: rgba(0, 0, 0, .45); font-size: 15px; line-height: 1;
                 width: 20px; padding: 0; }
  .slot button:hover { color: rgba(0, 0, 0, .8); }
  .slot.fixed { padding-right: 8px; }

  .add { width: 30px; height: var(--chip-height); border-radius: var(--chip-radius);
         border: none; cursor: pointer; background: var(--fill);
         color: var(--secondary-text-color); font-size: 16px; font-family: inherit; }
  .add[disabled] { opacity: .35; cursor: default; }

  .foot { display: flex; align-items: center; gap: 8px; margin-top: 14px; }
  button.action { height: var(--chip-height); padding: 0 14px; border: none;
           border-radius: var(--chip-radius); cursor: pointer; font-family: inherit;
           font-size: 12px; font-weight: 500; background: var(--fill);
           color: var(--primary-text-color); }
  button.action[disabled] { opacity: .4; cursor: default; }
  button#save:not([disabled]) { background: var(--primary-color);
           color: var(--text-primary-color); }
  .msg { font-size: 12px; flex: 1; color: var(--secondary-text-color); }
  .msg.error { color: var(--error-color); }
  .msg.ok { color: var(--success-color, green); }
  .msg.warn { color: var(--warning-color, orange); }
`;

const toMinutes = (hhmm) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

const toClock = (minutes) =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(
    minutes % 60
  ).padStart(2, "0")}`;

const refuse = (code, message) => Object.assign(new Error(message), { code });

/* The setpoint a day holds at a minute, which is the last slot before it. */
export const inChargeAt = (slots, minute) => {
  let held = null;
  for (const slot of slots) {
    if (toMinutes(slot.time) <= minute) held = slot.temperature;
  }
  return held;
};

/* Where the week is now : which day it is and how far into it, in the
 * browser's own clock. getDay() counts from Sunday, DAYS from Monday. */
export const nowInWeek = (date = new Date()) => ({
  day: DAYS[(date.getDay() + 6) % 7],
  minute: date.getHours() * 60 + date.getMinutes(),
});

/* The three rules build_matrix enforces, enforced here too so a day is
 * refused while it is still on screen rather than after Save has written the
 * six days before it.
 */
const checked = (slots) => {
  const times = slots.map((slot) => slot.time);
  if (new Set(times).size !== times.length) {
    throw refuse("duplicate", "Two slots cannot start at the same time");
  }
  if (!times.includes("00:00")) {
    throw refuse("midnight", "A day has to start at 00:00");
  }
  return [...slots].sort((a, b) => toMinutes(a.time) - toMinutes(b.time));
};

/* Change one slot, or drop it when `change` is null. Pure, and exported, so
 * tests/test_schedule_card.mjs can hold these to the rules without a
 * browser. */
export const writeSlot = (slots, index, change) => {
  const next = slots.map((slot) => ({ ...slot }));
  if (change === null) {
    next.splice(index, 1);
  } else {
    next[index] = { ...next[index], ...change };
  }
  return checked(next);
};

/* A new slot lands in the middle of the longest stretch the day leaves
 * empty, holding whatever was already in charge there : adding one should
 * change nothing until somebody sets it to something. */
export const addSlot = (slots) => {
  if (slots.length >= MAX_SLOTS) {
    throw refuse("full", `A day holds ${MAX_SLOTS} slots at most`);
  }

  const starts = slots.map((slot) => toMinutes(slot.time)).sort((a, b) => a - b);
  const bounds = [...starts, 24 * 60];
  let widest = 0;
  let at = 0;
  for (let index = 0; index < starts.length; index++) {
    const gap = bounds[index + 1] - bounds[index];
    if (gap > widest) {
      widest = gap;
      // Rounded to the half hour, which is how a program is usually written,
      // and never onto the slot that opens the gap.
      at = Math.max(
        bounds[index] + 1,
        Math.round((bounds[index] + gap / 2) / 30) * 30
      );
    }
  }

  return checked([
    ...slots,
    { time: toClock(at), temperature: inChargeAt(slots, at) },
  ]);
};

// The card's base in a browser, and something importable outside one : the
// pure helpers above are held to their rules by tests/test_schedule_card.mjs,
// which runs in node and has no DOM.
const CardBase = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

class CozytouchScheduleCard extends CardBase {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("cozytouch-schedule-card needs an `entity`");
    }
    this._config = { program: "heating", min: 5, max: 30, step: 0.5, ...config };
    this._days = null;
    this._language = null;
    this._open = false;
    this._dirty = new Set();
    this._status = "";
  }

  /* Rendering is driven by edits, not by state changes : a rebuild on every
   * poll would take the focus out of the field while somebody is typing. */
  set hass(hass) {
    const language = hass.language || "en";
    if (language !== this._language) {
      this._language = language;
      this._labels = dayNames(language);
      // Anything before the dash is a language Home Assistant offers and the
      // card does not : fr-CA falls back to fr before it falls back to en.
      this._t = STRINGS[language] || STRINGS[language.split("-")[0]] || STRINGS.en;
    }

    this._hass = hass;
    // Closed, the head is a clock : nothing is focused, so redrawing it on a
    // state update is what keeps it from going stale without a timer.
    if (this._days === null) this._load();
    else if (!this._open) this._render();
  }

  getCardSize() {
    return 8;
  }

  async _load() {
    this._days = {};
    try {
      const result = await this._hass.callWS({
        type: "call_service",
        domain: "cozytouch",
        service: "get_schedule",
        service_data: { program: this._config.program },
        target: { entity_id: this._config.entity },
        return_response: true,
      });
      this._days = result.response[this._config.entity].days;
    } catch (err) {
      this._status = `error|${this._say(err)}`;
    }
    this._render();
  }

  /* An error the card raised itself carries a code and is said in the
   * reader's language; anything from Home Assistant or the network is
   * repeated as it came. */
  _say(err) {
    const template = err.code && this._t[err.code];
    return template
      ? template.replace("%s", MAX_SLOTS)
      : err.message || String(err);
  }

  _temperaturesInUse() {
    const seen = new Set();
    for (const slots of Object.values(this._days || {})) {
      for (const slot of slots) seen.add(slot.temperature);
    }
    return [...seen].sort((a, b) => a - b);
  }

  /* Blue where it is coldest, red where it is warmest, through sand rather
   * than through the spectrum, and across the setpoints the program actually
   * uses rather than the config's min and max. See docs/decisions.md. */
  _colour(temperature) {
    if (temperature === null) return "var(--divider-color)";

    const COLD = [124, 165, 214];
    const MID = [240, 213, 138];
    const WARM = [214, 106, 84];

    const used = this._temperaturesInUse();
    const low = Math.min(...used, temperature);
    const high = Math.max(...used, temperature);
    const ratio = high === low ? 0 : (temperature - low) / (high - low);

    const [from, to, t] =
      ratio < 0.5 ? [COLD, MID, ratio * 2] : [MID, WARM, (ratio - 0.5) * 2];
    const mix = from.map((v, i) => Math.round(v + (to[i] - v) * t));
    return `rgb(${mix.join(",")})`;
  }

  _apply(day, produce) {
    const before = JSON.stringify(this._days[day]);
    try {
      this._days[day] = produce(this._days[day]);
    } catch (err) {
      this._status = `warn|${this._say(err)}`;
      return this._render();
    }

    if (JSON.stringify(this._days[day]) !== before) this._dirty.add(day);
    this._status = "";
    this._render();
  }

  async _save() {
    this._status = `busy|${this._t.writing}`;
    this._render();
    try {
      for (const day of this._dirty) {
        await this._hass.callService("cozytouch", "set_schedule", {
          entity_id: this._config.entity,
          program: this._config.program,
          days: [day],
          slots: this._days[day],
        });
      }
      this._dirty.clear();
      this._status = `ok|${this._t.written}`;
    } catch (err) {
      this._status = `error|${this._say(err)}`;
    }
    this._render();
  }

  _render() {
    if (!this._shadow) this._shadow = this.attachShadow({ mode: "open" });

    const [kind, message] = this._status.split("|");
    const days = DAYS.filter((day) => this._days[day]);
    const title = this._config.title || `${this._config.program} program`;
    const body =
      days.length === 0 ? this._empty(kind, message) : this._week(days, kind, message);

    this._shadow.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head" id="head">
          <h2>${title}</h2>
          ${this._nowChip()}
          <span class="caret">${this._open ? "\u25B2" : "\u25BC"}</span>
        </div>
        ${this._open || this._dirty.size ? `<div class="week">${body}</div>` : ""}
      </ha-card>`;

    this._bind();
  }

  /* What the program holds at this minute, on today's day. Absent while the
   * card is still loading, or for a program the device reports without the
   * day we are in. */
  _nowChip() {
    const { day, minute } = nowInWeek();
    const slots = this._days?.[day];
    if (!slots) return "";
    const temperature = inChargeAt(slots, minute);
    if (temperature === null) return "";
    return `<div class="now" style="background:${this._colour(temperature)}">
      <span class="at">${toClock(minute)}</span>
      <span>${temperature.toLocaleString(this._language)}°</span>
    </div>`;
  }

  _empty(kind, message) {
    return `<div class="msg ${kind || ""}">${message || this._t.loading}</div>`;
  }

  _week(days, kind, message) {
    const pending = this._dirty.size;
    return `
      ${days.map((day) => this._row(day)).join("")}
      <div class="foot">
        <button class="action" id="save" ${pending ? "" : "disabled"}>${
          this._t.save
        }${pending ? ` (${pending})` : ""}</button>
        <button class="action" id="reload">${this._t.reload}</button>
        <div class="msg ${kind || ""}">${message || ""}</div>
      </div>`;
  }

  _row(day) {
    const slots = this._days[day];
    const chips = slots
      .map((slot, index) => {
        // 00:00 is the one slot build_matrix insists on, so it has no
        // remove button rather than a button that always refuses.
        const fixed = slot.time === "00:00";
        return `<div class="slot ${fixed ? "fixed" : ""}"
                  style="background:${this._colour(slot.temperature)}">
          <input type="time" value="${slot.time}"
                 data-day="${day}" data-index="${index}" data-field="time">
          <input type="number" value="${slot.temperature}"
                 min="${this._config.min}" max="${this._config.max}"
                 step="${this._config.step}"
                 data-day="${day}" data-index="${index}" data-field="temperature">
          <span class="unit">°</span>
          ${
            fixed
              ? ""
              : `<button data-drop="${day}" data-index="${index}"
                   title="${this._t.remove}">×</button>`
          }
        </div>`;
      })
      .join("");

    const full = slots.length >= MAX_SLOTS;
    return `<div class="day">
      <div class="name">${this._labels[day]}</div>
      <div class="slots">
        ${chips}
        <button class="add" data-add="${day}" ${full ? "disabled" : ""}
                title="${full ? this._t.full.replace("%s", MAX_SLOTS) : this._t.add}"
                >+</button>
      </div>
    </div>`;
  }

  _bind() {
    const root = this._shadow;

    root.querySelectorAll("input[data-field]").forEach((el) =>
      el.addEventListener("change", () => {
        const { day, index, field } = el.dataset;
        const value = field === "time" ? el.value : Number(el.value);
        // An emptied time field parses as "", which would leave the day
        // without the slot the user is still editing.
        if (field === "time" && !value) return this._render();
        this._apply(day, (slots) =>
          writeSlot(slots, Number(index), { [field]: value })
        );
      })
    );

    root.querySelectorAll("[data-drop]").forEach((el) =>
      el.addEventListener("click", () =>
        this._apply(el.dataset.drop, (slots) =>
          writeSlot(slots, Number(el.dataset.index), null)
        )
      )
    );

    root.querySelectorAll("[data-add]").forEach((el) =>
      el.addEventListener("click", () =>
        this._apply(el.dataset.add, (slots) => addSlot(slots))
      )
    );

    root.getElementById("head").addEventListener("click", () => {
      this._open = !this._open;
      this._render();
    });

    root.getElementById("save")?.addEventListener("click", () => this._save());
    root.getElementById("reload")?.addEventListener("click", () => {
      this._days = null;
      this._dirty.clear();
      this._status = "";
      this.hass = this._hass;
    });
  }
}

// Guarded so the pure helpers above can be imported by node, which has
// neither a custom element registry nor a window.
if (typeof customElements !== "undefined") {
  customElements.define("cozytouch-schedule-card", CozytouchScheduleCard);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "cozytouch-schedule-card",
    name: "Cozytouch Schedule",
    description: "Edit a device's own weekly heating or cooling program",
  });
}
