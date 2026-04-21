# JavaScript Temporal API — Playground

A small sandbox exploring the modern **JavaScript Temporal API** (the upcoming replacement for `Date`). Uses `@js-temporal/polyfill` so it runs today, before native browser support.

![JavaScript](https://img.shields.io/badge/JavaScript-ES2024-F7DF1E?logo=javascript&logoColor=black)
![Temporal](https://img.shields.io/badge/Temporal-polyfill-8957e5)

## What's here

The script walks through the Temporal API operations that map to things you used to do with `Date`, `moment`, or `dayjs`:

- Creating plain dates (`Temporal.PlainDate`)
- Getting the current date (`Temporal.Now.plainDateISO()`)
- Comparing dates (`.equals()`)
- Differences between dates (`.since()`)
- Adding durations (`.add({ days, months, years })`)

## Why bother with Temporal?

`Date` has famous problems — months are 0-indexed, timezone handling is a trap, mutation by reference, no real duration math. Temporal fixes all of that with an immutable, timezone-aware, strongly-typed API. It's the first real replacement the language has had in 30 years.

## Quick start

```bash
git clone https://github.com/Hassan-Naeem-code/Temporal-API.git
cd Temporal-API

yarn install
yarn start     # snowpack dev server
```

Open `index.html` and check the console for the output.

## Files

```
.
├── index.html       # page that loads the script
├── script.js        # main Temporal walk-through
├── x.js / y.js      # extra Temporal experiments
├── package.json     # @js-temporal/polyfill, snowpack
└── README.md
```

## Learn more

- MDN: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Temporal
- Proposal: https://github.com/tc39/proposal-temporal
- Polyfill used: https://www.npmjs.com/package/@js-temporal/polyfill

## License

MIT
