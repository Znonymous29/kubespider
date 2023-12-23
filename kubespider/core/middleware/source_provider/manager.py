import _thread
import logging
import time

from flask import Flask

from core.middleware.manager import AbsManager
from core.middleware.source_provider import providers
from core.middleware.source_provider.sdk_source_provider.provider import SdkSourceProvider
from utils.types import ProviderType
from utils.values import SourceProviderApi


class SourceManager(AbsManager):

    def reload_instance(self):
        instance = {}
        for ins_conf in self.get_instance_confs():
            if ins_conf.get("enable"):
                conf = ins_conf["conf"]
                init_params = {item.get("name"): item.get("value") for item in conf.get("instance_params")}
                instance[ins_conf["id"]] = SdkSourceProvider(
                    bin_path=conf.get("bin"),
                    pid=ins_conf["id"],
                    **init_params)
                logging.info(f"[SourceManager] {ins_conf.get('instance_name')} enabled, waiting for active ...")
        self.instance = instance
        logging.info("[SourceManager] instance reload success ...")

    @staticmethod
    def get_specs():
        specs = []
        for sp in providers:
            specs += sp.spec()
        return specs

    def __init__(self, app: Flask = None):
        self.provider_type = ProviderType.source_provider
        self.instance = {}
        if app:
            self.init_app(app)

    def init_app(self, app: Flask):
        if "source_manager" in app.extensions:
            raise RuntimeError(
                "A 'Source Manager' instance has already been registered on this Flask app."
                " Import and use that instance instead."
            )
        with app.app_context():
            app.extensions["source_manager"] = self
            self.reload_instance()
            _thread.start_new_thread(self.output_skd_provider_log, ())

    def active_provider_instance(self, **kwargs):
        pid = kwargs.get("pid")
        instance = self.instance.get(pid)
        if not instance:
            return False
        return instance.active(**kwargs)

    def search(self, keyword, sync=False, **kwargs):
        result = []
        for key, instance in self.instance.items():
            if SourceProviderApi.search in instance.apis:
                try:
                    resp = instance.search(sync, keyword=keyword, **kwargs)
                    result += resp.get("data", [])
                except Exception as err:
                    logging.error(f"[SourceProvider {instance.name}] search failed: %s", err)
        return result

    def schedule(self, sync=False, **kwargs):
        result = []
        for key, instance in self.instance.items():
            if SourceProviderApi.schedule in instance.apis:
                try:
                    resp = instance.search(sync, **kwargs)
                    result += resp.get("data", [])
                except Exception as err:
                    logging.error(f"[SourceProvider {instance.name}] schedule failed: %s", err)
        return result

    def output_skd_provider_log(self):
        while True:
            for key, instance in self.instance.items():
                if isinstance(instance, SdkSourceProvider):
                    sub_process = instance.process
                    lines = sub_process.stdout.readlines() + sub_process.stderr.readlines()
                    for line in [l.strip() for l in lines]:
                        logging.info("[%s] %s", instance.name, line)
            time.sleep(0.5)
