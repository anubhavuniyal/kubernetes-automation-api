from fastapi import FastAPI, HTTPException, Query, APIRouter
from fastapi.responses import RedirectResponse
from controller import KubernetesController


app = APIRouter()
controller = KubernetesController()



@app.get("/", include_in_schema=False)
def docs_redirect():
    return RedirectResponse(url='/docs')

@app.get("/connect")
def connect_to_cluster(context: str = None):
    try:
        if context is None:
            return {"contexts": controller.list_contexts()}
        controller.connect_cluster(context)
        return {"message": f"Connected to the {context} cluster successfully."}
    except HTTPException as e:
        raise e

@app.get("/install")
def install_dependencies(
    metric_server: bool = Query(False), keda: bool = Query(False), remoteValues = Query(None), values = Query(None)
):
    try:
        return controller.install_dependencies(metric_server, keda, remoteValues, values)
    except HTTPException as e:
        raise e


@app.get("/verify")
def verify_dependencies():
    try:
        return controller.verify_installation()
    except HTTPException as e:
        raise e


@app.get("/deploy")
def deploy_application(
    namespace: str,
    image_name: str,
    version: str,
    port: int
):
    try:
        return controller.deploy_application(namespace, image_name, version, port)
    except HTTPException as e:
        raise e


@app.get("/autoscale")
def apply_autoscaling(
    namespace: str, deployment: str = None
):
    try:
        return controller.apply_autoscaling(namespace, deployment)
    except HTTPException as e:
        raise e


@app.get("/status")
def get_status(namespace: str, deployment: str = None):
    try:
        return controller.get_deployment_status(namespace, deployment)
    except HTTPException as e:
        raise e
