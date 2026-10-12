// A page store of named values with subscribers - the system filters, the parts' counts, the active part. The marking
// store's shape for things that are not markings: made by the page, handed to the parts that read or write a name.

export class KeyedStore {
  constructor(initial = {}) {
    this.values = new Map(Object.entries(initial));
    this.listeners = new Map();
  }
  get(name) { return this.values.get(name); }
  names() { return [...this.values.keys()]; }
  set(name, value) {
    this.values.set(name, value);
    for (const fn of [...(this.listeners.get(name) || []), ...(this.listeners.get('*') || [])]) fn(name, value);
  }
  /** `name` '*' hears every name. Returns the unsubscribe. */
  subscribe(name, fn) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(fn);
    return () => this.listeners.get(name).delete(fn);
  }
}
