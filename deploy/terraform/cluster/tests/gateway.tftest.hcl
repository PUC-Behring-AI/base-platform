# Renders the cluster's manifests without AWS or a cluster: every provider is
# mocked and the EKS module's outputs are fixed. Run by tests/test_terraform.py
# and the gate workflow with `terraform test`.

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

run "gateway_class_is_internet_facing_by_default" {
  command = plan

  assert {
    condition     = yamldecode(kubectl_manifest.gateway_lb_config.yaml_body).spec.scheme == "internet-facing"
    error_message = "the Gateway's load balancer is not internet-facing by default"
  }

  assert {
    condition = yamldecode(kubectl_manifest.gateway_class.yaml_body).spec.parametersRef == {
      group     = "gateway.k8s.aws"
      kind      = "LoadBalancerConfiguration"
      name      = "base-alb"
      namespace = "kube-system"
    }
    error_message = "GatewayClass base-alb does not point at its LoadBalancerConfiguration"
  }

  assert {
    condition     = yamldecode(kubectl_manifest.gateway_class.yaml_body).spec.controllerName == "eks.amazonaws.com/gateway-alb"
    error_message = "GatewayClass base-alb is not Auto Mode's ALB Gateway controller"
  }
}

run "gateway_scheme_internal" {
  command = plan

  variables {
    gateway_scheme = "internal"
  }

  assert {
    condition     = yamldecode(kubectl_manifest.gateway_lb_config.yaml_body).spec.scheme == "internal"
    error_message = "gateway_scheme is not passed to the LoadBalancerConfiguration"
  }
}

run "gateway_scheme_refuses_other_values" {
  command = plan

  variables {
    gateway_scheme = "public"
  }

  expect_failures = [var.gateway_scheme]
}
