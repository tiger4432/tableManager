// The fake webmail (lead 11-07). Same mails on every load (seeded); the URL never changes.
//   list       25 more items each time the list is scrolled near its end, 0.5 s later, up to 200
//   open       a click fills the pane 0.2-2 s later; until then the pane keeps what it had (the last body, hidden or not)
//   never      every 11th item from the 8th (ids 8, 19, 30, ...) never loads
//   hidden     a closed pane is hidden one of four ways, in turn by item id (HIDES)
const TOTAL = 200, BATCH = 25;
const HIDES = [["reader", "hide-height"], ["reader", "hide-opacity"], ["reader", "hide-offscreen"],
               ["reader-wrap", "hide-fold"]];
const WORDS = ["wafer", "lot", "yield", "map", "tool", "chamber", "recipe", "shift", "review", "hold", "release", "die"];
const PEOPLE = ["kim", "lee", "park", "choi", "jung"];

function seeded(seed) {
  return () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
}

function mail(id) {
  const rand = seeded(id * 7919);
  const pick = (list) => list[Math.floor(rand() * list.length)];
  const words = (n) => Array.from({ length: n }, () => pick(WORDS)).join(" ");
  const subject = words(3).replace(/^./, (c) => c.toUpperCase()) + " #" + id;
  const minute = 600 + id * 7;
  return { id, subject, from: pick(PEOPLE) + "@bench.test", body: words(60), unread: rand() < 0.4,
           date: "2026-11-" + String(1 + (id % 28)).padStart(2, "0") + " " +
                 String(Math.floor(minute / 60) % 24).padStart(2, "0") + ":" + String(minute % 60).padStart(2, "0") };
}

const items = document.getElementById("mail-items");
const list = document.getElementById("mail-list");
const status = document.getElementById("list-status");
let shown = 0, loading = false, hidden = HIDES[0], asked = 0;

function more() {
  if (loading || shown >= TOTAL) return;
  loading = true;
  status.textContent = "Loading...";
  setTimeout(() => {
    for (const end = Math.min(shown + BATCH, TOTAL); shown < end;) {
      const m = mail(++shown);
      const row = document.createElement("div");
      row.className = "mail-item" + (m.unread ? " unread" : "");
      row.dataset.id = m.id;
      row.innerHTML = '<span class="mail-from"></span><span class="mail-date"></span><div class="mail-subject"></div>';
      row.querySelector(".mail-from").textContent = m.from;
      row.querySelector(".mail-date").textContent = m.date;
      row.querySelector(".mail-subject").textContent = m.subject;
      items.appendChild(row);
    }
    loading = false;
    status.textContent = shown >= TOTAL ? "No more mail" : "";
  }, 500);
}

function hide(on) {
  document.getElementById(hidden[0]).classList.toggle(hidden[1], on);
}

items.addEventListener("click", (event) => {
  const row = event.target.closest(".mail-item");
  if (!row) return;
  const m = mail(Number(row.dataset.id)), ask = ++asked;
  row.classList.remove("unread");
  if (m.id % 11 === 8) return;
  setTimeout(() => {
    if (ask !== asked) return;
    const pane = document.getElementById("reader");
    pane.querySelector(".reader-subject").textContent = m.subject;
    pane.querySelector(".reader-from").textContent = m.from;
    pane.querySelector(".reader-date").textContent = m.date;
    pane.querySelector(".reader-id").textContent = String(m.id);
    pane.querySelector(".reader-body").textContent = m.body;
    hide(false);
    hidden = HIDES[m.id % HIDES.length];
  }, 200 + Math.random() * 1800);
});

document.getElementById("reader-close").addEventListener("click", () => hide(true));
list.addEventListener("scroll", () => {
  if (list.scrollTop + list.clientHeight > list.scrollHeight - 200) more();
});
more();
