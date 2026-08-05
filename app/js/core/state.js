// View state that is not part of the URL: filters, metric controls, cached selections.
const DEFAULTS = {
  threshold: "5.0A", weighting: "unit_weighted_continuous", cohort: "all_eligible",
  stateFilter: "", speciesFilter: "", methodFilter: "", receptorFilter: "",
  siteClass: "", search: "", page: 0, pageSize: 50
};
let s = Object.assign({}, DEFAULTS);
const subs = [];
export function get() { return s; }
export function set(patch, silent) {
  s = Object.assign({}, s, patch);
  if (!silent) for (const fn of subs) fn(s);
}
export function resetFilters() {
  s = Object.assign({}, s, { stateFilter: "", speciesFilter: "", methodFilter: "",
    receptorFilter: "", search: "", page: 0 });
}
export function subscribe(fn) { subs.push(fn); }
export function defaults() { return Object.assign({}, DEFAULTS); }
