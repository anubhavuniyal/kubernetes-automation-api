# Kubernetes Management API

This FastAPI-based API simplifies Kubernetes cluster management by automating common tasks such as:

Connecting to a Kubernetes cluster.
Installing dependencies like Metrics Server and KEDA.
Deploying container images from DockerHub.
Applying KEDA-based autoscaling on deployments.
Fetching deployment and pod metrics.

Designed with a Model-View-Controller (MVC) architecture, this API ensures modularity, scalability, and maintainability.
Features

1. Connect to Kubernetes Cluster

        Endpoint: /connect
Description:
        Connect to a specific Kubernetes cluster using a provided context.
        Lists all available contexts if none is provided.

Purpose:
        Simplifies cluster management, especially for multi-cluster environments.

2. Install Dependencies

        Endpoint: /install
Description:
        Installs essential dependencies such as:
            Metrics Server (required for resource-based autoscaling).
            KEDA (enables event-driven autoscaling).

Production Recommendations:
        Use Helm for better customization and maintainability.
        Pin dependency versions to ensure compatibility.

3. Verify Dependencies

        Endpoint: /verify
Description:
        Confirms the installation of Metrics Server and KEDA.
        Ensures prerequisites for scaling are operational.

4. Deploy Container Images

        Endpoint: /deploy
Description:
        Deploys a container image from DockerHub with:
            Configurable ports.
            KEDA-based autoscaling (triggers: CPU and Memory).
        Creates a NodePort service to expose the application.
Production Recommendations:
        Use ClusterIP services with Ingress for secure access.
        Add resource requests and limits based on thorough testing to avoid cluster resource exhaustion and resource starvation for the pods.

5. Autoscale Deployment

        Endpoint: /autoscale
Description:
        Enables or updates KEDA-based autoscaling for a deployment.
        Supports CPU and memory triggers by default.
Production Recommendations:
        Monitor scaling metrics with tools like Prometheus and Grafana.
        To use full capabilities of KEDA-based autoscaling, look into other metric sources like Apache MSK, DynamoDB etc. 

6. Fetch Deployment Status

        Endpoint: /status
    Description:
        Fetches the status of a deployment or all deployments in a namespace.
        Provides pod readiness and overall health details.

Architecture

This API follows the Model-View-Controller (MVC) architecture:

    Model:
        Handles Kubernetes API interactions.
        Encapsulates logic for cluster connection, deployment, and autoscaling.
        File: model.py

    Controller:
        Bridges user requests (via views) to the models.
        Ensures clean separation of concerns.
        File: controller.py

    View:
        Defines RESTful endpoints using FastAPI.
        Handles user inputs and responses.
        File: views.py

    App Initialization:
        Integrates all components and starts the API server.
        File: app.py

Installation and Setup
1. Prerequisites

    Python 3.8+
    Kubernetes cluster with:
        Sufficient permissions to manage deployments, services, and custom resources.
    Install dependencies:
        pip -r requirements.txt

2. Run the Application

    Start the API server:

    fastapi run app.py

    Access the API at http://127.0.0.1:8000.

Usage
1. Connect to a Cluster

    GET /connect

        Response:
    
        {
        "contexts": ["minikube", "staging-cluster", "prod-cluster"]
        }

2. Install Dependencies

    GET /install?metric_server=true&keda=true

        Response:
    
        {
        "installed": ["Metrics Server installed successfully.", "KEDA installed successfully."]
        }

3. Deploy a Container

    POST /deploy?namespace=default&image_name=nginx&version=latest&port=80

        Response:
    
        {
         "message": "Deployment nginx-latest created successfully."
        }

4. Apply Autoscaling

    POST /autoscale?namespace=default&deployment=nginx-latest

        Response:

        {
        "message": "Autoscaling applied successfully."
        }

5. Check Deployment Status

    GET /status?namespace=default&deployment=nginx-latest

        Response:
    
        {
        "deployment": "nginx-latest",
        "ready_replicas": 3,
        "available_replicas": 3
        }


Best Practices for Production
1. Dependency Management

Use Helm for installing Container Images.
Store and version values.yaml files in a repository.

2. Networking

Replace NodePort services with ClusterIP and configure an Ingress Controller.

3. Security

Restrict API access using authentication (e.g., OAuth2).
Implement RBAC policies for fine-grained access control.

4. Monitoring

Integrate Prometheus and Grafana for resource and autoscaling monitoring.
Set up alerts for high resource utilization.

5. Resource Management

Define resource limits and requests for all deployments to prevent cluster exhaustion.

## Conclusion

This API provides a robust foundation for managing Kubernetes clusters and deploying applications with autoscaling. By adhering to best practices and incorporating production-grade enhancements, this solution can efficiently manage workloads in any Kubernetes environment.
