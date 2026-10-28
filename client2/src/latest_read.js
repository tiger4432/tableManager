// One read at a time on a board (lead 10-28 «기제 하나 · 판 둘»): a newer question cuts the read out - its answer is
// another question's - and the same question asked while its read is out is asked once more when it ends, not again
// beside it. Two boards live on state: the grid's rows (a page, a sort, a filter, a table, a jump) and the history
// sidebar (Global, Row, Cell).
export class ReadBoard {
  constructor() {
    this.ticket = 0;
    this.abort = null;
    this.out = null;
  }

  /** A new question: the read out is cut. Its ticket - the signal to read with, and whether it is still the board's. */
  begin() {
    this.ticket += 1;
    if (this.abort) this.abort.abort();
    this.abort = new AbortController();
    this.out = null;
    const mine = this.ticket;
    return { signal: this.abort.signal, current: () => mine === this.ticket };
  }

  /** `read(ticket)` for `question` now - or, while that question's read is out, once more when it ends. */
  ask(question, read) {
    if (this.out && this.out.question === question) {
      this.out.again = true;
      return this.out.done;
    }
    const ticket = this.begin();
    const out = { question, again: false, done: null };
    this.out = out;
    out.done = (async () => {
      try {
        do {
          out.again = false;
          await read(ticket);
        } while (out.again && ticket.current());
      } finally {
        if (this.out === out) this.out = null;
      }
    })();
    return out.done;
  }
}
