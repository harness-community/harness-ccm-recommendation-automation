# harness ccm recommendation automation

automatically link harness ccm recommendations to jira

## setup

you will need a csv file to define the mapping of Cost Category buckets to JIRA configurations.

```csv
<Bucket>,<JIRA Project>,<Recommendation Issue Type>,<Anomaly Issue Type>,<Reporter>
```

Then you need to set the Cost Category to use for the bucket definitions using `COST_CATEGORY` environment variable.

A recommendation that falls under a bucket listed in the CSV for the given Cost Category will result in a JIRA item created matching the spec from the line in the CSV.

## Configuration

- `CSV_FILE`: mapping of buckets to JIRA configuration
- `JIRA_CONNECTOR_REF`: connector ID of JIRA connector to use, must start with `account.`
- `COST_CATEGORY`: cost category name for which buckets are searched from
- `HARNESS_URL`: url of harness instance (eg. `app.harness.io`)
- `HARNESS_ACCOUNT_ID`: harness account id (eg. `xyz123`)
- `HARNESS_PLATFORM_API_KEY`: harness api key (eg. `sat.xyz123.XXXXXXXXX`)
