from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.utils import create_from_yaml
from fastapi import HTTPException
import tempfile
import requests
import subprocess
from shutil import which


class KubernetesCluster:
    def __init__(self):
        self.api_client = None
        self.apps_v1 = None
        self.core_v1 = None
        self.autoscaling_v1 = None
        self.helm = which("helm")

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

    def install_dependencies(self, metric_server=False, keda=False):
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
                    chart="bitnami/nginx",
                    namespace="default",
                    values={"replicaCount": 2, "service.type": "LoadBalancer"}
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

    def install_chart(self, release_name: str, chart: str, namespace: str = "default", values: dict = None, remote_values: str = None):
        """
        Installs a Helm chart.
        :param release_name: The name of the Helm release.
        :param chart: The chart name or URL (e.g., stable/nginx-ingress or path to a chart directory).
        :param namespace: The Kubernetes namespace to install the chart in.
        :param values: A dictionary of custom values for the Helm chart.
        :return: Output from the Helm install command.
        """
        try:
            # Prepare the Helm command
            cmd = [self.helm_executable, "upgrade", "--install", release_name, chart, "--namespace", namespace, "--create-namespace"]

            # Add custom values if provided
            if remote_values:

                cmd.extend(["-f", "values.yaml"])
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

    def deploy_image(self, namespace, image_name, version, port, scale_metric="cpu,memory"):
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
                "type": "ClusterIP",
            },
        }

        try:
            self.apps_v1.create_namespaced_deployment(namespace, deployment_manifest)
            self.core_v1.create_namespaced_service(namespace, service_manifest)
        except ApiException as e:
            raise HTTPException(status_code=500, detail=f"Error creating deployment: {e.body}")

        return {"message": f"Deployment {deployment_name} created successfully."}

    def autoscale_deployment(self, namespace, deployment=None, scale_metric="cpu,memory"):
        """
        Autoscale a deployment using KEDA or HPA.
        """

        def apply_hpa(deployment_name):
            hpa_manifest = {
                "apiVersion": "autoscaling/v1",
                "kind": "HorizontalPodAutoscaler",
                "metadata": {"name": deployment_name, "namespace": namespace},
                "spec": {
                    "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": deployment_name},
                    "minReplicas": 1,
                    "maxReplicas": 10,
                    "targetCPUUtilizationPercentage": 80,
                },
            }
            try:
                self.autoscaling_v1.create_namespaced_horizontal_pod_autoscaler(namespace, hpa_manifest)
            except ApiException as e:
                raise HTTPException(status_code=500, detail=f"Error creating HPA: {e.body}")

        if deployment:
            apply_hpa(deployment)
        else:
            deployments = self.apps_v1.list_namespaced_deployment(namespace)
            for deploy in deployments.items:
                apply_hpa(deploy.metadata.name)

        return {"message": "Autoscaling applied successfully."}

    def pause_autoscale(self, namespace, deployment=None):
        """
        Pause autoscaling for a deployment or namespace.
        """
        return {"message": "Paused autoscaling."}

    def get_status(self, namespace, deployment=None):
        """
        Get the status of a deployment or all deployments in a namespace.
        """

        if deployment:
            deployment_obj = self.apps_v1.read_namespaced_deployment(deployment, namespace)
            return {
                "deployment": deployment,
                "ready_replicas": deployment_obj.status.ready_replicas,
                "available_replicas": deployment_obj.status.available_replicas,
            }
        else:
            deployments = self.apps_v1.list_namespaced_deployment(namespace)
            return [
                {
                    "name": deploy.metadata.name,
                    "ready_replicas": deploy.status.ready_replicas,
                    "available_replicas": deploy.status.available_replicas,
                }
                for deploy in deployments.items
            ]
