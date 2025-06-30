from os import getenv
import csv
import logging

from requests import post

# if we are being used as a drone plugin, prefix env with SETTING_
if getenv("DRONE_OUTPUT"):
    env_prefix = "SETTING_"
else:
    env_prefix = ""


def get_env(key: str, default: str = "") -> str:
    return getenv(f"{env_prefix}{key}", default)


# Settings for API calls to Harness
PARAMS = {
    "routingId": get_env("HARNESS_ACCOUNT_ID"),
    "accountIdentifier": get_env("HARNESS_ACCOUNT_ID"),
}

HEADERS = {
    "x-api-key": get_env("HARNESS_PLATFORM_API_KEY"),
}

HARNESS_URL = get_env("HARNESS_URL")

logging.basicConfig(level=get_env("LOG_LEVEL", "INFO"))


class RecommendationBuckets:
    """
    Custom class to represent data needed to link recommendation to JIRA
    """

    def __init__(
        self,
        CostBucket: str,
        JiraProject: str,
        RecommendationType: str,
        AnomalyType: str,
        Reporter: str,
    ):
        self.CostBucket = CostBucket
        self.JiraProject = JiraProject
        self.RecommendationType = RecommendationType
        self.AnomalyType = AnomalyType
        self.Reporter = Reporter

    def __repr__(self):
        return f"{self.CostBucket}:{self.JiraProject} Recommendation:{self.RecommendationType} Anomaly:{self.AnomalyType} {self.Reporter}"


def write_outputs(outputs: dict[str, str]):
    """
    write key value outputs to a local file to be rendered in the plugin step

    args:
        outputs (dict[str, str]): string to string mappings
    """

    if not (filename := getenv("DRONE_OUTPUT")):
        logging.debug("DRONE_OUTPUT environment variable not set")
        return

    output_file = open(filename, "a")

    for k, v in outputs.items():
        output_file.write(f"{k}={v}\n")

    output_file.close()


def get_count() -> int:
    """
    Get total count of recommendations
    """
    resp = post(
        f"https://{HARNESS_URL}/gateway/ccm/api/recommendation/overview/count",
        params=PARAMS,
        headers=HEADERS,
        json={
            "daysBack": 4,
            "minSaving": 1,
            "filterType": "CCMRecommendation",
            "perspectiveFilters": [],
            "k8sRecommendationFilterPropertiesDTO": {"recommendationStates": ["OPEN"]},
        },
    )

    resp.raise_for_status()

    return resp.json()["data"]


def get_recommendations(limit: int = 10, offset: int = 0) -> int:
    """
    Get all recommendations in an account which are not already tied to JIRA or SNOW
    """

    resp = post(
        f"https://{HARNESS_URL}/gateway/ccm/api/recommendation/overview/list",
        params=PARAMS,
        headers=HEADERS,
        json={
            "daysBack": 4,
            "minSaving": 1,
            "filterType": "CCMRecommendation",
            "perspectiveFilters": [],
            "k8sRecommendationFilterPropertiesDTO": {"recommendationStates": ["OPEN"]},
            "offset": offset,
            "limit": limit,
        },
    )

    resp.raise_for_status()

    results = [
        x
        for x in resp.json()["data"]["items"]
        if (x["jiraConnectorRef"] == None) and (x["servicenowConnectorRef"] == None)
    ]

    if len(results) == limit:
        results.extend(get_recommendations(limit, offset + limit))

    return results


def get_ag_rule(rule_id: str) -> str:
    """
    Get YAML of a governance rule
    """

    resp = post(
        f"https://{HARNESS_URL}/gateway/ccm/api/governance/rule/list",
        params=PARAMS,
        headers=HEADERS,
        json={"query": {"policyIds": [rule_id]}},
    )

    resp.raise_for_status()

    return resp.json()["data"]["rules"][0]["rulesYaml"]


def link(
    recommendation: dict,
    connectorRef: str,
    projectKey: str,
    issueType: str,
    dryRun: bool = False,
):
    """
    Create JIRA ticket fields and link to recommendation
    """

    # create summary (titles)
    if recommendation["resourceType"] == "EC2_INSTANCE":
        summary = f"Resizing {recommendation['resourceName']}"
        description = (
            f"||*Instance Name*|{recommendation['resourceName']}|\n||*Account Name*|{recommendation['namespace']}|\n||*Potential Monthly Savings*|*${round(recommendation['monthlySaving'], 2)}*|\n||*Recommendation Link*|[https://{HARNESS_URL}/ng/account/{PARAMS['accountIdentifier']}/module/ce/recommendations/ec2/{recommendation['id']}/name/{recommendation['resourceName']}/details]|",
        )
    elif recommendation["resourceType"] == "GOVERNANCE":
        summary = f"Monthly potential savings of ${round(recommendation['monthlySaving'], 2)} in {recommendation['namespace']} ({recommendation['resourceName']})"
        rule_yaml = get_ag_rule(recommendation["governanceRuleId"])
        description = f"||*Cloud Provider*|{recommendation['cloudProvider']}|\n||*Region*|{recommendation['targetRegion']}|\n||*Cloud Account*|{recommendation['namespace']}|\n||*Rule Name*|{recommendation['resourceName']}|\n||*Resource Type*|{recommendation['recommendationDetails']['resourceType']}|\n||*Action Type*|{recommendation['recommendationDetails']['actionType']}|\n||*Rule YAML*|{{code:yaml}}{rule_yaml}{{code}}|\n||*Potential Savings*|*${recommendation['recommendationDetails']['executions'][0]['potentialSavings']}*|\n||*Resource Count*|{recommendation['recommendationDetails']['executions'][0]['resourceCount']}|\n||*Recommendation Link*|[https://{HARNESS_URL}/ng/account/{PARAMS['accountIdentifier']}/module/ce/recommendations/governance/{recommendation['id']}/name/{recommendation['resourceName']}/details]|"
    elif recommendation["resourceType"] == "AZURE_INSTANCE":
        summary = f"Rightsize {recommendation['resourceName']}"
        description = f"||*Subscription*|{recommendation['clusterName']}|\n||*Resource Group*|{recommendation['namespace']}|\n||*VM*|{recommendation['resourceName']}|\n||*Potential Monthly Savings*|*${recommendation['monthlySaving']}*|\n||*Recommendation Link*|[https://{HARNESS_URL}/ng/account/{PARAMS['accountIdentifier']}/module/ce/recommendations/azure/{recommendation['id']}/name/{recommendation['resourceName']}/details]|"
    elif recommendation["resourceType"] == "WORKLOAD":
        summary = f"Rightsize {recommendation['resourceName']}"
        description = f"||*Workload name*|{recommendation['resourceName']}|\n||*Cluster name*|{recommendation['clusterName']}|\n||*Namespace*|{recommendation['namespace']}|\n||*Potential Monthly Savings*|*${recommendation['monthlySaving']}*|\n||*Recommendation Link*|[https://{HARNESS_URL}/ng/account/{PARAMS['accountIdentifier']}/module/ce/recommendations/{recommendation['id']}/name/{recommendation['resourceName']}/details]|"
    elif recommendation["resourceType"] == "NODE_POOL":
        summary = f"Rightsize {recommendation['resourceName']}"
        description = f"||*Nodepool name*|{recommendation['resourceName']}|\n||*Cluster name*|{recommendation['clusterName']}|\n||*Region*|{recommendation['targetRegion']}|\n||*Current Instance Family*|{recommendation['recommendationDetails']['nodePoolId']['nodepoolname']}|\n||*Potential Monthly Savings*|*${recommendation['monthlySaving']}*|\n||*Recommendation Link*|[https://{HARNESS_URL}/ng/account/{PARAMS['accountIdentifier']}/module/ce/recommendations/node/{recommendation['id']}/name/{recommendation['resourceName']}/details]|"
    if recommendation["resourceType"] == "ECS_SERVICE":
        summary = f"Resizing {recommendation['resourceName']}"
        description = (
            f"||*Service Name*|{recommendation['resourceName']}|||*Account Name*|{recommendation['namespace']}|||*Cluster Name*|{recommendation['clusterName']}|||*ECS Launch Type*|{recommendation['recommendationDetails']['launchType']}|||*Potential Monthly Savings*|*${recommendation['monthlySaving']}*|||*Recommendation Link*|[https://{HARNESS_URL}/ng/account/{PARAMS['accountIdentifier']}/module/ce/recommendations/ecs/{recommendation['id']}/name/{recommendation['resourceName']}/details]|",
        )

    if dryRun:
        logging.info(f"\n\n{summary}:\n{description}")
    else:
        resp = post(
            f"https://{HARNESS_URL}/gateway/ccm/api/recommendation/jira/create",
            params=PARAMS,
            headers=HEADERS,
            json={
                "connectorRef": connectorRef,
                "projectKey": projectKey,
                "issueType": issueType,
                "fields": {
                    "summary": summary,
                    "description": description,
                    "components": "Non-PS",
                },
                "recommendationId": recommendation["id"],
                "resourceType": recommendation["resourceType"],
            },
        )

        resp.raise_for_status()

        return resp.json()


def load_csv(filename: str) -> dict:
    """
    Load in mapping CSV into Objects
    """

    mappings = {}

    with open(filename, mode="r", newline="") as file:
        csv_reader = csv.reader(file)

        for row in csv_reader:
            # cc name to information
            mappings[row[0]] = RecommendationBuckets(
                row[0], row[1], row[2], row[3], row[4]
            )

    return mappings


if __name__ == "__main__":
    return_code = 0
    return_data = {}

    # load in category mapping from csv
    mappings = load_csv(get_env("CSV_FILE"))
    for cc in mappings:
        logging.debug(mappings[cc])

    # get recommendations
    all_reccs = get_recommendations()
    min_savings = float(get_env("MIN_SAVINGS", "0.0"))

    for recc in all_reccs:
        # Skip if recommendation savings are below threshold
        if recc.get("monthlySaving", 0) < min_savings:
            logging.debug(
                f"Skipping recommendation {recc.get('id')} - savings ${recc.get('monthlySaving')} below threshold ${min_savings}"
            )
            continue

        # find the bucket for this recommendation
        buckets = [
            x["costBucket"]
            for x in recc["costCategoryDetails"]
            if x["costCategory"] == get_env("COST_CATEGORY")
        ]
        if not buckets:
            logging.error(f"Bucket mapping not found for recommendation {recc['id']}")
            return_code = 1
            continue

        bucket = buckets.pop()
        if bucket not in mappings:
            logging.error(f"Bucket mapping not found for {bucket}")
            return_code = 1
            continue

        jiraInfo = mappings[bucket]

        resp = link(
            recc,
            get_env("JIRA_CONNECTOR_REF"),
            jiraInfo.JiraProject,
            jiraInfo.RecommendationType,
            dryRun=get_env("DRY_RUN"),
        )

        logging.debug(resp)

        return_data[recc["id"]] = resp

    write_outputs(return_data)
    exit(return_code)
