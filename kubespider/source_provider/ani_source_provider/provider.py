# This works for: https://open.ani.rip
# Function: download anime updated on ANi project
# encoding:utf-8
import logging
import traceback

import xml.etree.ElementTree as ET
import re
from typing import Tuple

from source_provider import provider
from api import types
from api.values import Event, Resource
from utils import helper
from utils.config_reader import AbsConfigReader

class AniSourceProvider(provider.SourceProvider):
    '''This provider is to sync resources from ANi API: https://api.ani.rip/ani-download.xml
    For the most timely follow-up of Anime updates.
    Downloading media in general HTTP, aria2 provider must be needed.
    '''
    def __init__(self, name: str, config_reader: AbsConfigReader) -> None:
        super().__init__(config_reader)
        self.provider_listen_type = types.SOURCE_PROVIDER_PERIOD_TYPE
        self.link_type = types.LINK_TYPE_GENERAL
        self.webhook_enable = False
        self.provider_type = 'ani_source_provider'
        self.api_type = 'http'
        self.rss_link = ''
        self.rss_link_torrent = ''
        self.tmp_file_path = '/tmp/'
        self.save_path = 'ANi'
        self.provider_name = name
        self.classification_on_directory = True
        self.detect_season = False
        self.blacklist = []
        self.custom_season_mapping = {}

    def get_provider_name(self) -> str:
        return self.provider_name

    def get_provider_type(self) -> str:
        return self.provider_type

    def get_provider_listen_type(self) -> str:
        return self.provider_listen_type

    def get_download_provider_type(self) -> str:
        return None
    
    def get_season(self, title: str) -> tuple[int, str]:
        season = 1
        keyword = None
        mapper = {
            "第二季": 2,
            "第三季": 3,
            "第四季": 4,
            "第五季": 5,
            "第六季": 6,
            "第七季": 7,
            "第八季": 8,
            "第九季": 9,
            "第十季": 10
        }
        # The user-defined season_mapping has higher priority
        for kw in mapper:
            if kw in title:
                season = mapper[kw]
                keyword = kw
        for kw in self.custom_season_mapping:
            if kw in title:
                season = self.custom_season_mapping[kw]
                keyword = kw

        return season, keyword

    def rename_season(self, title, season, keyword) -> str:
        new_title = title.replace(f" {keyword}", "")
        regex_pattern = r"- (\d+) \[(720P|1080P|4K)\]\[(Baha|Bilibili)\]"
        s_ = str(season).zfill(2)
        output = re.sub(regex_pattern, rf"- S{s_}E\1 [\2][\3]", new_title)
        return output

    def get_prefer_download_provider(self) -> list:
        downloader_names = self.config_reader.read().get('downloader', None)
        if downloader_names is None:
            return None
        if isinstance(downloader_names, list):
            return downloader_names
        return [downloader_names]

    def get_download_param(self) -> dict:
        return self.config_reader.read().get('download_param', {})

    def get_link_type(self) -> str:
        return self.link_type

    def provider_enabled(self) -> bool:
        return self.config_reader.read().get('enable', True)

    def is_webhook_enable(self) -> bool:
        return self.webhook_enable

    def should_handle(self, event: Event) -> bool:
        return False

    def get_links(self, event: Event) -> list[Resource]:
        try:
            req = helper.get_request_controller()
            links_data = req.get(self.rss_link, timeout=30).content
        except Exception as err:
            logging.info('Error while fetching ANi API: %s', err)
            return []
        tmp_xml = helper.get_tmp_file_name('') + '.xml'
        with open(tmp_xml, 'wb') as cfg_file:
            cfg_file.write(links_data)
            cfg_file.close()
        blacklist = self.load_filter_config()
        return self.get_links_from_xml(tmp_xml, blacklist)

    def get_links_from_xml(self, tmp_xml, blacklist) -> list[Resource]:
        try:
            xml_parse = ET.parse(tmp_xml)
            items = xml_parse.findall('.//item')
            path = self.save_path
            ret = []
            for i in items:
                xml_title = i.find('./title').text
                item_title, item_episode, extra = self.get_anime_info(xml_title)
                season, season_keyword = self.get_season(xml_title)
                url = i.find('./guid').text
                if item_title is not None:
                    logging.info('Found Anime "%s" Season %s Episode %s with info %s', item_title, season, item_episode, extra)
                    if not self.check_blacklist(xml_title, blacklist):
                        path_ = path + (f'/{item_title}' if self.classification_on_directory else '')
                        res = Resource(
                            url=url,
                            path=path_,
                            file_type=types.FILE_TYPE_VIDEO_TV,
                            link_type=self.get_link_type(),
                        )
                        if season > 1:
                            res.put_extra_params(
                                {'file_name': self.rename_season(xml_title, season, season_keyword)}
                            )
                        ret.append(res)
                else:
                    continue
            return ret
        except Exception as err:
            print(traceback.format_exc())
            logging.info('Error while parsing RSS XML: %s', err)
            return []

    def get_anime_info(self, title: str) -> Tuple[str, str, tuple]:
        '''Extract info by only REGEX, might be wrong in extreme cases.
        '''
        pattern = re.compile(r'\[ANi\] (.+?) - (\d+) \[(.+?)\]\[(.+?)\]\[(.+?)\]\[(.+?)\]\[(.+?)\]\.')
        matches = pattern.findall(title)
        try:
            title, episode = matches[0][:2]
            extra_info = matches[0][2:]
            return title, episode, extra_info
        except Exception as err:
            logging.warning('Error while running regex on title %s: %s', title, err)
            return None, None, None

    def load_filter_config(self) -> str:
        filter_ = self.config_reader.read().get('blacklist', None)

        if filter_ is None or filter_ == "":
            return []
        if isinstance(filter_, list):
            return [str(item) for item in filter_]
        if isinstance(filter_, str):
            return [filter_]
        logging.warning('Invalid blacklist value: %s, fallback to Empty', filter_)
        return []

    def check_blacklist(self, text: str, blacklist: list) -> bool:
        for item in blacklist:
            if item in text:
                logging.info('File %s will be ignored due to blacklist matched: %s', text, item)
                return True
        return False

    def update_config(self, event: Event) -> None:
        pass

    def load_config(self) -> None:
        cfg = self.config_reader.read()
        logging.info('ANi rss link is: %s', cfg['rss_link'])
        self.rss_link = cfg['rss_link']
        self.classification_on_directory = cfg.get('classification_on_directory', True)
