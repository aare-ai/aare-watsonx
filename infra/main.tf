terraform {
  required_version = ">= 1.0"

  required_providers {
    ibm = {
      source  = "IBM-Cloud/ibm"
      version = "~> 1.60"
    }
  }
}

provider "ibm" {
  ibmcloud_api_key = var.ibmcloud_api_key
  region           = var.region
}

variable "ibmcloud_api_key" {
  description = "IBM Cloud API Key"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "IBM Cloud region"
  type        = string
  default     = "us-south"
}

variable "environment" {
  description = "Environment name (prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "aare-ai"
}

# Get resource group
data "ibm_resource_group" "group" {
  name = var.resource_group_name
}

# Cloud Object Storage instance
resource "ibm_resource_instance" "cos" {
  name              = "aare-ai-cos-${var.environment}"
  service           = "cloud-object-storage"
  plan              = "standard"
  location          = "global"
  resource_group_id = data.ibm_resource_group.group.id

  tags = ["aare-ai", var.environment]
}

# COS bucket for ontologies
resource "ibm_cos_bucket" "ontologies" {
  bucket_name          = "aare-ai-ontologies-${var.environment}"
  resource_instance_id = ibm_resource_instance.cos.id
  region_location      = var.region
  storage_class        = "smart"

  object_versioning {
    enable = true
  }
}

# Service credentials for COS
resource "ibm_resource_key" "cos_key" {
  name                 = "aare-ai-cos-key-${var.environment}"
  role                 = "Writer"
  resource_instance_id = ibm_resource_instance.cos.id

  parameters = {
    HMAC = true
  }
}

# Code Engine project
resource "ibm_code_engine_project" "aare" {
  name              = "aare-ai-${var.environment}"
  resource_group_id = data.ibm_resource_group.group.id
}

# Container Registry namespace
resource "ibm_cr_namespace" "aare" {
  name              = "aare-ai-${var.environment}"
  resource_group_id = data.ibm_resource_group.group.id
}

# Code Engine secret for COS credentials
resource "ibm_code_engine_secret" "cos_credentials" {
  project_id = ibm_code_engine_project.aare.project_id
  name       = "cos-credentials"
  format     = "generic"

  data = {
    IBM_COS_API_KEY      = ibm_resource_key.cos_key.credentials["apikey"]
    IBM_COS_INSTANCE_CRN = ibm_resource_instance.cos.id
    IBM_COS_ENDPOINT     = "https://s3.${var.region}.cloud-object-storage.appdomain.cloud"
    ONTOLOGY_BUCKET      = ibm_cos_bucket.ontologies.bucket_name
  }
}

# Code Engine application
resource "ibm_code_engine_app" "verify" {
  project_id      = ibm_code_engine_project.aare.project_id
  name            = "aare-ai-verify"
  image_reference = "icr.io/${ibm_cr_namespace.aare.name}/aare-ai-verify:latest"

  scale_min_instances     = 0
  scale_max_instances     = 10
  scale_cpu_limit         = "2"
  scale_memory_limit      = "4G"
  scale_request_timeout   = 30

  run_env_variables {
    type  = "literal"
    name  = "ENVIRONMENT"
    value = var.environment
  }

  run_env_variables {
    reference = ibm_code_engine_secret.cos_credentials.name
    type      = "secret_full_reference"
  }
}

# Outputs
output "app_url" {
  description = "The URL of the deployed application"
  value       = ibm_code_engine_app.verify.endpoint
}

output "cos_bucket" {
  description = "The COS bucket for ontologies"
  value       = ibm_cos_bucket.ontologies.bucket_name
}

output "container_registry" {
  description = "The container registry namespace"
  value       = ibm_cr_namespace.aare.name
}

output "project_id" {
  description = "The Code Engine project ID"
  value       = ibm_code_engine_project.aare.project_id
}
