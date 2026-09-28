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


https://allyprod.service-now.com/api/now/table/change_request?sysparm_query=priorityIN1,2^active=true^ORDERBYDESCsys_created_on&sysparm_fields=number,short_description,priority,risk,state,start_date,end_date,assignment_group&sysparm_display_value=true&sysparm_limit=100