from model import KubernetesCluster


class KubernetesController:
    def __init__(self):
        self.cluster = KubernetesCluster()

    def connect_cluster(self, context=None):
        self.cluster.connect(context)

    def list_contexts(self):
        return self.cluster.get_contexts()

    def install_dependencies(self, metric_server, keda, remoteValues, values):
        return self.cluster.install_dependencies(metric_server, keda, remoteValues, values)

    def verify_installation(self):
        return self.cluster.verify_installation()

    def deploy_application(self, namespace, image_name, version, port, scale_metric):
        return self.cluster.deploy_image(namespace, image_name, version, port, scale_metric)

    def apply_autoscaling(self, namespace, deployment, scale_metric):
        return self.cluster.autoscale_deployment(namespace, deployment, scale_metric)

    def get_deployment_status(self, namespace, deployment):
        return self.cluster.get_status(namespace, deployment)
