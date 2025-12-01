# aare.ai - IBM Cloud Code Engine Deployment

IBM Cloud Code Engine implementation of the aare.ai Z3 SMT verification engine.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    IBM Cloud Code Engine                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    /verify endpoint                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────────┐     │   │
│  │  │   LLM    │→ │ Ontology │→ │   Z3 SMT Verifier  │     │   │
│  │  │  Parser  │  │  Loader  │  │  (Constraint Logic)│     │   │
│  │  └──────────┘  └──────────┘  └────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│                   IBM Cloud Object Storage                      │
│                   (aare-ai-ontologies/*.json)                   │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- [IBM Cloud CLI](https://cloud.ibm.com/docs/cli)
- [Docker](https://docs.docker.com/get-docker/)
- [Terraform](https://www.terraform.io/downloads) (for infrastructure deployment)
- Python 3.11+
- An IBM Cloud account with Code Engine and COS enabled

## Project Structure

```
aare-watsonx/
├── app.py                       # Flask application entry point
├── Dockerfile                   # Container image definition
├── handlers/
│   ├── __init__.py
│   ├── llm_parser.py            # LLM output text parser
│   ├── formula_compiler.py      # Compile JSON formulas to Z3
│   ├── ontology_loader.py       # Loads rules from IBM COS
│   └── smt_verifier.py          # Z3 theorem prover engine
├── ontologies/                  # Compliance rule definitions
├── infra/
│   ├── main.tf                  # Terraform infrastructure
│   └── terraform.tfvars.example # Example variables
├── .github/
│   └── workflows/
│       └── deploy.yml           # CI/CD pipeline
├── requirements.txt             # Python dependencies
├── LICENSE
└── README.md
```

## Local Development

### 1. Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run locally

```bash
python app.py
```

Or with gunicorn:

```bash
gunicorn --bind 0.0.0.0:8080 app:app
```

The API will be available at `http://localhost:8080`

### 3. Test the endpoint

```bash
curl -X POST http://localhost:8080/verify \
  -H "Content-Type: application/json" \
  -d '{
    "llm_output": "Based on your DTI of 35% and FICO score of 720, you are approved for a $350,000 mortgage.",
    "ontology": "mortgage-compliance-v1"
  }'
```

### 4. Build and run with Docker

```bash
docker build -t aare-ai-verify .
docker run -p 8080:8080 aare-ai-verify
```

## Deployment

### Option 1: GitHub Actions (Recommended)

1. **Add GitHub secrets**:
   - `IBM_CLOUD_API_KEY`: Your IBM Cloud API key

2. Push to `main` or manually trigger the workflow

### Option 2: Manual Deployment with IBM Cloud CLI

```bash
# Login to IBM Cloud
ibmcloud login --apikey YOUR_API_KEY -r us-south

# Install plugins
ibmcloud plugin install container-registry
ibmcloud plugin install code-engine

# Create resource group (if needed)
ibmcloud resource group-create aare-ai

# Create Code Engine project
ibmcloud ce project create --name aare-ai-prod

# Create COS instance and bucket
ibmcloud resource service-instance-create aare-ai-cos cloud-object-storage standard global
ibmcloud cos bucket-create --bucket aare-ai-ontologies-prod --region us-south

# Login to Container Registry
ibmcloud cr region-set us-south
ibmcloud cr namespace-add aare-ai-prod
ibmcloud cr login

# Build and push image
docker build -t icr.io/aare-ai-prod/aare-ai-verify:latest .
docker push icr.io/aare-ai-prod/aare-ai-verify:latest

# Create secret for COS credentials
ibmcloud ce secret create --name cos-credentials \
  --from-literal IBM_COS_API_KEY=your-cos-api-key \
  --from-literal IBM_COS_INSTANCE_CRN=your-cos-crn \
  --from-literal IBM_COS_ENDPOINT=https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --from-literal ONTOLOGY_BUCKET=aare-ai-ontologies-prod

# Deploy application
ibmcloud ce app create --name aare-ai-verify \
  --image icr.io/aare-ai-prod/aare-ai-verify:latest \
  --min-scale 0 \
  --max-scale 10 \
  --cpu 2 \
  --memory 4G \
  --request-timeout 30 \
  --env-from-secret cos-credentials
```

### Option 3: Terraform

```bash
cd infra

# Create terraform.tfvars
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your API key

# Initialize and apply
terraform init
terraform plan
terraform apply
```

## API Reference

### POST /verify

Verifies LLM output against compliance constraints.

**Request:**
```json
{
  "llm_output": "Your LLM-generated text here",
  "ontology": "mortgage-compliance-v1"
}
```

**Response:**
```json
{
  "verified": true,
  "violations": [],
  "warnings": ["Variables defaulted (not found in input): ['variable_name']"],
  "parsed_data": {
    "dti": 35,
    "credit_score": 720,
    "loan_amount": 350000
  },
  "ontology": {
    "name": "mortgage-compliance-v1",
    "version": "1.0.0",
    "constraints_checked": 5
  },
  "proof": {
    "method": "Z3 SMT Solver",
    "version": "4.12.1"
  },
  "verification_id": "uuid",
  "execution_time_ms": 45,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**Note:** The `warnings` field appears when variables couldn't be extracted from the LLM output and were defaulted.

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "aare.ai"
}
```

## Formula Syntax

Constraints use structured JSON formulas that compile directly to Z3 expressions:

| Operator | Syntax | Example |
|----------|--------|---------|
| And | `{"and": [...]}` | `{"and": [{"<=": ["x", 10]}, {">=": ["y", 0]}]}` |
| Or | `{"or": [...]}` | `{"or": [{"==": ["approved", true]}, {">=": ["score", 700]}]}` |
| Not | `{"not": {...}}` | `{"not": {"==": ["has_phi", true]}}` |
| Implies | `{"implies": [A, B]}` | `{"implies": [{"==": ["is_denial", true]}, {"==": ["has_reason", true]}]}` |
| If-Then-Else | `{"ite": [cond, then, else]}` | `{"ite": [{">": ["score", 700]}, "approved", "denied"]}` |
| Equals | `{"==": [a, b]}` | `{"==": ["status", true]}` |
| Less/Greater | `{"<=": [a, b]}` | `{"<=": ["dti", 43]}` |
| Min/Max | `{"min": [a, b]}` | `{"<=": ["fee", {"min": [500, {"*": ["loan", 0.03]}]}]}` |

## Example Ontologies

| Ontology | Domain | Constraints | Description |
|----------|--------|-------------|-------------|
| `hipaa-v1` | Healthcare | 52 | HIPAA Privacy & Security Rule |
| `mortgage-compliance-v1` | Lending | 5 | ATR/QM, HOEPA, UDAAP, Reg B |
| `medical-safety-v1` | Healthcare | 5 | Drug interactions, dosing limits |
| `financial-compliance-v1` | Finance | 5 | Investment advice, disclaimers |
| `fair-lending-v1` | Lending | 5 | DTI limits, credit score requirements |

## Security

- Code Engine applications are private by default
- Use IBM Cloud IAM for authentication
- CORS restricted to aare.ai domains
- COS bucket access controlled via service credentials

### Making the Application Public

By default, Code Engine apps require authentication. To make it public:

```bash
ibmcloud ce app update --name aare-ai-verify --visibility public
```

## watsonx Integration

This deployment is designed to work alongside IBM watsonx.ai for LLM inference. Typical flow:

1. Your application calls watsonx.ai for LLM generation
2. The response is sent to aare.ai for compliance verification
3. Only verified responses are returned to the user

```python
# Example integration
import requests

# Generate with watsonx.ai
llm_response = watsonx_client.generate(prompt="...")

# Verify with aare.ai
verification = requests.post(
    "https://your-app.us-south.codeengine.appdomain.cloud/verify",
    json={
        "llm_output": llm_response,
        "ontology": "mortgage-compliance-v1"
    }
)

if verification.json()["verified"]:
    return llm_response
else:
    # Handle violation
    raise ComplianceError(verification.json()["violations"])
```

## Monitoring

- View logs: `ibmcloud ce app logs --name aare-ai-verify`
- IBM Cloud Console: https://cloud.ibm.com/codeengine

## Cost Estimation

Using Code Engine:
- vCPU: $0.00003440/vCPU-second
- Memory: $0.00000356/GB-second
- Free tier: 100,000 vCPU-seconds/month

Typical production usage (10,000 verifications/day): **~$10-20/month**

## License

MIT License - see [LICENSE](LICENSE) for details.
