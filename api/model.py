from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.utils import create_from_yaml
from fastapi import HTTPException
import tempfile
import requests
import re
import subprocess
from shutil import which


class KubernetesCluster:
    def __init__(self):
        self.api_client = None
        self.apps_v1 = None
        self.core_v1 = None
        self.autoscaling_v1 = None
        self.helm_executable = which("helm")

    def connect(self, context=None):
        """
        Load the Kubernetes configuration for the given context.
        """
        try:
            if context:
                config.load_kube_config(context=context)
            self.api_client = client.ApiClient()
            self.apps_v1 = client.AppsV1Api(self.api_client)
            self.core_v1 = client.CoreV1Api(self.api_client)
            self.autoscaling_v1 = client.AutoscalingV1Api(self.api_client)
            self.custom_api = client.CustomObjectsApi()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to connect to the cluster: {str(e)}")

    def get_contexts(self):
        """
        List all available Kubernetes contexts from the kubeconfig.
        """
        try:
            contexts, _ = config.list_kube_config_contexts()
            return [ctx["name"] for ctx in contexts]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching contexts: {str(e)}")

    def install_dependencies(self, metric_server, keda, remoteValues, values):
        """
        Install dependencies like Metrics Server, and KEDA.
        """
        results = []

        if metric_server:
            try:
                self.apply_yaml_from_url("https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml")
                results.append("Metrics Server installed successfully.")
            except ApiException as e:
                raise HTTPException(status_code=500, detail=f"Failed to install Metrics Server: {e.body}")

        if keda:
            try:
                self.install_chart(
                    release_name="keda",
                    chart_name="keda",
                    namespace="keda",
                    chart_url="https://kedacore.github.io/charts",
                    values=values,
                    remoteValues=remoteValues
                )
                results.append("KEDA installed successfully.")
            except ApiException as e:
                raise HTTPException(status_code=500, detail=f"Failed to install KEDA: {e.body}")

        return {"installed": results}
    
    def apply_yaml_from_url(self, url: str):
        """
        Applies a Kubernetes manifest from a remote URL.
        """
        try:
            # Fetch YAML content from the URL
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch YAML from URL: {e}")

        # Save YAML content to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name

        try:
            # Apply the YAML using Kubernetes Python client
            create_from_yaml(self.api_client, temp_file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to apply Kubernetes manifest: {e}")
        finally:
            # Clean up the temporary file
            args = ('rm', temp_file_path)
            subprocess.call('%s %s' % args, shell=True)
    
    def get_github_raw_content(self,url: str):
        """
        Fetch raw content from a GitHub URL (whether direct raw or parsed from a GitHub page URL).
        
        :param url: GitHub URL (raw or page URL)
        :return: Content of the file (str)
        """
        raw_url = url
        # Convert the GitHub URL to raw format if it's not already raw
        if url.startswith("https://github.com"):
            raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob", "")
        
        try:
            # Send a GET request to the raw GitHub file URL
            response = requests.get(raw_url)
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Return the content of the file
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"Error fetching file: {e}")
            return None


    def install_chart(self, release_name: str, chart_name: str, chart_url: str, namespace: str = "default", values: dict = None, remoteValues: str = None):
        """
        Installs a Helm chart.
        :param release_name: The name of the Helm release.
        :param chart: The chart name or URL (e.g., stable/nginx-ingress or path to a chart directory).
        :param namespace: The Kubernetes namespace to install the chart in.
        :param values: A dictionary of custom values for the Helm chart.
        :return: Output from the Helm install command.
        """
        try:
            # Add repo and update
            cmd = [self.helm_executable, "repo", "add", release_name, chart_url]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            cmd = [self.helm_executable, "repo", "update", release_name]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            # Prepare the Helm command
            cmd = [self.helm_executable, "upgrade", "--install", release_name, f"{release_name}/{chart_name}", "--namespace", namespace, "--create-namespace"]

            # Add custom values if provided
            if remoteValues:
                values = self.get_github_raw_content(remoteValues)
                cmd.extend(["-f", values])
            elif values:
                for key, value in values.items():
                    cmd.extend(["--set", f"{key}={value}"])

            # Run the Helm command
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return {"message": result.stdout.strip()}
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"Helm command failed: {e.stderr.strip()}")


    def check_deployment_exists(self,namespace, name):
            try:
                self.apps_v1.read_namespaced_deployment(name, namespace)
                return True
            except ApiException:
                return False

    def verify_installation(self):
        """
        Verify the installation of Metrics Server, and KEDA.
        """

        return {
            "metrics_server": self.check_deployment_exists("kube-system", "metrics-server"),
            "keda": self.check_deployment_exists("keda", "keda-operator"),
        }

    def deploy_image(self, namespace, image_name, version, port):
        """
        Deploy a container image and set up autoscaling using KEDA.
        """

        deployment_name = f"{image_name.replace('/', '-')}-{version}"

        deployment_manifest = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": deployment_name, "namespace": namespace},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": deployment_name}},
                "template": {
                    "metadata": {"labels": {"app": deployment_name}},
                    "spec": {
                        "containers": [
                            {
                                "name": deployment_name,
                                "image": f"{image_name}:{version}",
                                "ports": [{"containerPort": port}],
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "128Mi"},
                                    "limits": {"cpu": "500m", "memory": "512Mi"},
                                },
                            }
                        ]
                    },
                },
            },
        }

        service_manifest = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": deployment_name, "namespace": namespace},
            "spec": {
                "selector": {"app": deployment_name},
                "ports": [{"protocol": "TCP", "port": port, "targetPort": port}],
                "type": "NodePort",
            },
        }

        scaled_object_manifest = {
            "apiVersion": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "metadata": {"name": f"{deployment_name}-scaledobject", "namespace": namespace},
            "spec": {
                "minReplicaCount" : 1,
                "scaleTargetRef": {
                    "name": deployment_name,
                    "kind": "Deployment",
                },
                "triggers": [
                    {
                        "type": "cpu",
                        "metricType": "Utilization",
                        "metadata": {
                            "value": "80"  # Scale when CPU exceeds 50%
                        }
                    },
                    {
                        "type": "memory",
                        "metricType": "Utilization",
                        "metadata": {
                            "value": "80"  # Scale when memory exceeds 50%
                        }
                    }
                ]
            }
        }

        try:
            self.apps_v1.create_namespaced_deployment(namespace, deployment_manifest)
            self.core_v1.create_namespaced_service(namespace, service_manifest)
            self.custom_api.create_namespaced_custom_object(
                group="keda.sh",           # KEDA's API group
                version="v1alpha1",            # KEDA's API version
                namespace=namespace,           # Namespace where the resource is created
                plural="scaledobjects",        # Plural name of the resource (scaledobjects)
                body=scaled_object_manifest    # The manifest content to apply
            )
        except ApiException as e:
            raise HTTPException(status_code=500, detail=f"Error creating deployment: {e.body}")

        return {"message": f"Deployment {deployment_name} created successfully."}

    def autoscale_deployment(self, namespace, deployment_name=None):
        """
        Autoscale a deployment using KEDA or HPA.
        """

        scaled_object_manifest = {
        "apiVersion": "keda.sh/v1alpha1",
        "kind": "ScaledObject",
        "metadata": {"name": f"{deployment_name}-scaledobject", "namespace": namespace},
        "spec": {
            "minReplicaCount" : 1,
            "scaleTargetRef": {
                "name": deployment_name,
                "kind": "Deployment",
            },
            "triggers": [
                {
                    "type": "cpu",
                    "metricType": "Utilization",
                    "metadata": {
                        "value": "80"  # Scale when CPU exceeds 50%
                    }
                },
                {
                    "type": "memory",
                    "metricType": "Utilization",
                    "metadata": {
                        "value": "80"  # Scale when memory exceeds 50%
                    }
                }
            ]
        }
    }
        try:
            self.custom_api.create_namespaced_custom_object(
                group="keda.sh",           # KEDA's API group
                version="v1alpha1",            # KEDA's API version
                namespace=namespace,           # Namespace where the resource is created
                plural="scaledobjects",        # Plural name of the resource (scaledobjects)
                body=scaled_object_manifest    # The manifest content to apply
            )
        except ApiException as e:
            raise HTTPException(status_code=500, detail=f"Error creating HPA: {e.body}")

        return {"message": "Autoscaling applied successfully."}

    def get_status(self, namespace, deployment=None):
        """
        Get the status of a deployment or all deployments in a namespace.
        """

        if deployment:
            deployment_obj = self.apps_v1.read_namespaced_deployment(deployment,namespace)
            return {
                "deployment": deployment,
                "ready_replicas": deployment_obj.status.ready_replicas,
                "available_replicas": deployment_obj.status.available_replicas
            }
        else:
            deployments = self.apps_v1.list_namespaced_deployment(namespace)
            return [
                {
                    "name": deploy.metadata.name,
                    "ready_replicas": deploy.status.ready_replicas,
                    "available_replicas": deploy.status.available_replicas
                }
                for deploy in deployments.items
            ]
