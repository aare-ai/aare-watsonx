"""
Ontology loader for aare.ai (IBM Cloud version)
Loads verification rules from IBM Cloud Object Storage or returns default if storage fails
"""
import json
import os
import logging
from functools import lru_cache

import ibm_boto3
from ibm_botocore.client import Config


class OntologyLoader:
    def __init__(self, bucket_name=None):
        self.bucket_name = bucket_name or os.environ.get(
            "ONTOLOGY_BUCKET", "aare-ai-ontologies"
        )
        self.cos_client = None

        # IBM COS credentials from environment
        cos_api_key = os.environ.get("IBM_COS_API_KEY", "")
        cos_instance_crn = os.environ.get("IBM_COS_INSTANCE_CRN", "")
        cos_endpoint = os.environ.get(
            "IBM_COS_ENDPOINT", "https://s3.us-south.cloud-object-storage.appdomain.cloud"
        )

        if cos_api_key and cos_instance_crn:
            try:
                self.cos_client = ibm_boto3.client(
                    "s3",
                    ibm_api_key_id=cos_api_key,
                    ibm_service_instance_id=cos_instance_crn,
                    config=Config(signature_version="oauth"),
                    endpoint_url=cos_endpoint
                )
            except Exception as e:
                logging.warning(f"Failed to initialize IBM COS client: {e}")

    @lru_cache(maxsize=10)
    def load(self, ontology_name):
        """Load ontology from IBM Cloud Object Storage or return default"""
        try:
            if self.cos_client:
                response = self.cos_client.get_object(
                    Bucket=self.bucket_name,
                    Key=f"{ontology_name}.json"
                )
                content = response["Body"].read().decode("utf-8")
                ontology = json.loads(content)
                return self._validate_ontology(ontology)
        except self.cos_client.exceptions.NoSuchKey if self.cos_client else Exception:
            logging.info(f"Ontology {ontology_name} not found in COS")
        except Exception as e:
            logging.warning(f"Failed to load from IBM COS: {str(e)}")

        # Return default ontology
        logging.info(f"Using default ontology for {ontology_name}")
        return self._get_default_ontology()

    def _validate_ontology(self, ontology):
        """Validate ontology structure"""
        required_fields = ["name", "version", "constraints", "extractors"]
        for field in required_fields:
            if field not in ontology:
                raise ValueError(f"Invalid ontology: missing {field}")
        return ontology

    def _get_default_ontology(self):
        """Return default mortgage compliance ontology"""
        return {
            "name": "mortgage-compliance-v1",
            "version": "1.0.0",
            "description": "U.S. Mortgage Compliance - Core constraints",
            "constraints": [
                {
                    "id": "ATR_QM_DTI",
                    "category": "ATR/QM",
                    "description": "Debt-to-income ratio requirements",
                    "formula_readable": "(dti ≤ 43) ∨ (compensating_factors ≥ 2)",
                    "variables": [
                        {"name": "dti", "type": "real"},
                        {"name": "compensating_factors", "type": "int"},
                    ],
                    "error_message": "DTI exceeds 43% without sufficient compensating factors",
                    "citation": "12 CFR § 1026.43(c)",
                },
                {
                    "id": "HOEPA_HIGH_COST",
                    "category": "HOEPA",
                    "description": "High-cost mortgage counseling requirement",
                    "formula_readable": "(fee_percentage < 8) ∨ counseling_disclosed",
                    "variables": [
                        {"name": "fee_percentage", "type": "real"},
                        {"name": "counseling_disclosed", "type": "bool"},
                    ],
                    "error_message": "HOEPA triggered - counseling disclosure required",
                    "citation": "12 CFR § 1026.32",
                },
                {
                    "id": "UDAAP_NO_GUARANTEES",
                    "category": "UDAAP",
                    "description": "Prohibition on guarantee language",
                    "formula_readable": "¬(has_guarantee ∧ has_approval)",
                    "variables": [
                        {"name": "has_guarantee", "type": "bool"},
                        {"name": "has_approval", "type": "bool"},
                    ],
                    "error_message": "Cannot guarantee approval",
                    "citation": "12 CFR § 1036.3",
                },
                {
                    "id": "HPML_ESCROW",
                    "category": "Escrow",
                    "description": "Escrow requirements based on FICO",
                    "formula_readable": "(credit_score ≥ 620) ∨ ¬escrow_waived",
                    "variables": [
                        {"name": "credit_score", "type": "int"},
                        {"name": "escrow_waived", "type": "bool"},
                    ],
                    "error_message": "Cannot waive escrow with FICO < 620",
                    "citation": "12 CFR § 1026.35(b)",
                },
                {
                    "id": "REG_B_ADVERSE",
                    "category": "Regulation B",
                    "description": "Adverse action disclosure requirements",
                    "formula_readable": "is_denial → has_specific_reason",
                    "variables": [
                        {"name": "is_denial", "type": "bool"},
                        {"name": "has_specific_reason", "type": "bool"},
                    ],
                    "error_message": "Must disclose specific denial reason",
                    "citation": "12 CFR § 1002.9",
                },
            ],
            "extractors": {
                "dti": {"type": "float", "pattern": "dti[:\\s~]*(\\d+(?:\\.\\d+)?)"},
                "credit_score": {
                    "type": "int",
                    "pattern": "(?:fico|credit score)[:\\s]*(\\d{3})",
                },
                "fees": {
                    "type": "money",
                    "pattern": "\\$?([\\d,]+)k?\\s*(?:fees?|costs?)",
                },
                "loan_amount": {
                    "type": "money",
                    "pattern": "\\$?([\\d,]+)k?\\s*(?:loan|mortgage)",
                },
                "has_guarantee": {
                    "type": "boolean",
                    "keywords": ["guaranteed", "100%", "definitely"],
                },
                "has_approval": {"type": "boolean", "keywords": ["approved", "approve"]},
                "counseling_disclosed": {
                    "type": "boolean",
                    "keywords": ["counseling"],
                },
                "escrow_waived": {
                    "type": "boolean",
                    "keywords": ["escrow waived", "waive escrow", "skip escrow"],
                },
                "is_denial": {
                    "type": "boolean",
                    "keywords": ["denied", "cannot approve"],
                },
                "has_specific_reason": {
                    "type": "boolean",
                    "keywords": ["credit", "income", "dti", "debt", "score"],
                },
            },
        }

    def list_available(self):
        """List all available ontologies"""
        try:
            if self.cos_client:
                response = self.cos_client.list_objects_v2(Bucket=self.bucket_name)
                return [
                    obj["Key"].replace(".json", "")
                    for obj in response.get("Contents", [])
                    if obj["Key"].endswith(".json")
                ]
        except Exception as e:
            logging.warning(f"Failed to list ontologies: {e}")
        return ["mortgage-compliance-v1"]
