# Examples

Drop sample contracts or listing agreements here to test the agent locally.

```
./run.sh examples/sample-contract.pdf
./run.sh examples/sample-listing.jpg
```

Real documents aren't checked into the repo — use redacted samples or
synthetic ones generated for testing.

Tip: a quick sanity-check is to take a screenshot of any real-estate
contract template, save it as `sample-contract.png`, and run the agent
against that. The vision model will fill in placeholder party names from
whatever the template uses (often "John Doe" / "Jane Doe").
