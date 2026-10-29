# The Bedrock role: one ServiceAccount may invoke exactly the model ARNs the
# caller lists, and nothing is created when the caller lists none. Every
# provider is mocked, as in gateway.tftest.hcl.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
}

mock_provider "kubectl" {}

override_module {
  target = module.eks
  outputs = {
    cluster_name                       = "test"
    cluster_arn                        = "arn:aws:eks:test:000000000000:cluster/test"
    cluster_endpoint                   = "https://example.invalid"
    cluster_certificate_authority_data = ""
    cluster_oidc_issuer_url            = "https://example.invalid"
    cluster_primary_security_group_id  = "sg-test"
    node_iam_role_name                 = "test-node"
  }
}

variables {
  name           = "test"
  region         = "test-region-1"
  vpc_id         = "vpc-test"
  subnet_ids     = ["subnet-a", "subnet-b"]
  secrets_prefix = "test/"
}

run "no_bedrock_access_by_default" {
  command = plan

  assert {
    condition     = length(aws_iam_role.bedrock) == 0 && length(aws_iam_role_policy.bedrock) == 0 && length(aws_eks_pod_identity_association.bedrock) == 0
    error_message = "a Bedrock role exists although bedrock_access is null"
  }

  assert {
    condition     = output.bedrock_role_arn == null
    error_message = "bedrock_role_arn is not null although bedrock_access is null"
  }
}

run "bedrock_access_grants_exactly_the_given_arns" {
  command = plan

  variables {
    bedrock_access = {
      namespace       = "llm"
      service_account = "gateway"
      model_arns = [
        "arn:aws:bedrock:test-region-1:000000000000:inference-profile/test.model-a",
        "arn:aws:bedrock:test-region-1::foundation-model/model-a",
        "arn:aws:bedrock:test-region-2::foundation-model/model-a",
      ]
    }
  }

  assert {
    condition     = length(data.aws_iam_policy_document.bedrock_invoke[0].statement) == 1
    error_message = "the Bedrock policy has more than one statement"
  }

  assert {
    condition = toset(data.aws_iam_policy_document.bedrock_invoke[0].statement[0].resources) == toset([
      "arn:aws:bedrock:test-region-1:000000000000:inference-profile/test.model-a",
      "arn:aws:bedrock:test-region-1::foundation-model/model-a",
      "arn:aws:bedrock:test-region-2::foundation-model/model-a",
    ])
    error_message = "the Bedrock policy does not list exactly the given model ARNs"
  }

  assert {
    condition     = toset(data.aws_iam_policy_document.bedrock_invoke[0].statement[0].actions) == toset(["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"])
    error_message = "the Bedrock policy allows other actions than InvokeModel and InvokeModelWithResponseStream"
  }

  assert {
    condition     = aws_eks_pod_identity_association.bedrock[0].namespace == "llm" && aws_eks_pod_identity_association.bedrock[0].service_account == "gateway"
    error_message = "the Pod Identity association is not for the given namespace and ServiceAccount"
  }

  assert {
    condition     = aws_eks_pod_identity_association.bedrock[0].cluster_name == "test"
    error_message = "the Pod Identity association is not on this cluster"
  }

  assert {
    condition     = aws_iam_role.bedrock[0].name == "test-bedrock"
    error_message = "the Bedrock role is not named <name>-bedrock"
  }
}

run "bedrock_access_refuses_an_empty_arn_list" {
  command = plan

  variables {
    bedrock_access = {
      namespace       = "llm"
      service_account = "gateway"
      model_arns      = []
    }
  }

  expect_failures = [var.bedrock_access]
}

run "bedrock_access_refuses_a_wildcard" {
  command = plan

  variables {
    bedrock_access = {
      namespace       = "llm"
      service_account = "gateway"
      model_arns      = ["arn:aws:bedrock:test-region-1::foundation-model/*"]
    }
  }

  expect_failures = [var.bedrock_access]
}
