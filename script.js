import { Temporal } from "@js-temporal/polyfill";

const now = new Temporal.PlainDate(2022, 1, 1);
console.log("now", now);

// Getting Current Date
const rightNow = Temporal.Now.plainDateISO();
console.log("rightNow", rightNow.toString());
// Compare by Getting Current Date
const compare = Temporal.Now.plainDateISO();
console.log("comparing", rightNow.equals(compare));
// Difference Between Two Dates
const difference = new Temporal.PlainDate(2022, 1, 1);
console.log("difference", rightNow.since(difference).toString());
// Adding Date to Current Date
const addDate = rightNow.add({ days: 2, months: 5, years: 12 }).toString();
console.log("addDate", addDate);
// Subtracting Date to Current Date
const subtractDate = rightNow
  .subtract({ days: 2, months: 5, years: 12 })
  .toString();
console.log("subtractDate", subtractDate);
// Subtracting Date to Current Date
const subtractDate = rightNow
  .subtract({ days: 2, months: 5, years: 12 })
  .toString();
console.log("subtractDate", subtractDate);
// Subtracting Date to Current Date
const subtractDate = rightNow
  .subtract({ days: 2, months: 5, years: 12 })
  .toString();
console.log("subtractDate", subtractDate);
// Subtracting Date to Current Date
const subtractDate = rightNow
  .subtract({ days: 2, months: 5, years: 12 })
  .toString();
console.log("subtractDate", subtractDate);
// Subtracting Date to Current Date
const subtractDate = rightNow
  .subtract({ days: 2, months: 5, years: 12 })
  .toString();
console.log("subtractDate", subtractDate);