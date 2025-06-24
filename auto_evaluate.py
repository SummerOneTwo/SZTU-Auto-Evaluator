import requests, random, sys, time, traceback, base64, urllib3
from configparser import ConfigParser
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from Crypto.Cipher import DES

urllib3.disable_warnings()

def pad(data, block_size=8):
    length = block_size - (len(data) % block_size)
    return data.encode(encoding='utf-8') + (chr(length) * length).encode(encoding='utf-8')

class Auth:
    cookies = {}
    ok = False

    def __init__(self, cookies=None):
        self.session = requests.session()
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ' \
                                             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36'
        self.session.headers['Host'] = 'auth.sztu.edu.cn'
        self.session.headers['Referer'] = 'https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu'
        self.session.headers['Origin'] = 'https://auth.sztu.edu.cn'
        self.session.headers['X-Requested-With'] = 'XMLHttpRequest'
        self.session.headers['Sec-Fetch-Site'] = 'same-origin'
        self.session.headers['Sec-Fetch-Mode'] = 'cors'
        self.session.headers['Sec-Fetch-Dest'] = 'empty'
        self.session.headers['sec-ch-ua-mobile'] = '?0'
        self.session.headers['sec-ch-ua-platform'] = '"macOS"'
        self.session.headers['sec-ch-ua'] = '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"'
        self.session.headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        if cookies:
            self.session.cookies = requests.utils.cookiejar_from_dict(cookies)
            self.check_login()

    def login(self, school_id, password):
        # 初始化 session
        self.session.headers['Host'] = 'jwxt.sztu.edu.cn'
        resp = self.get('https://jwxt.sztu.edu.cn/')
        resp = self.get(resp.headers['Location'])
        resp = self.get(resp.headers['Location'])

        self.session.headers['Host'] = 'auth.sztu.edu.cn'
        self.get(resp.headers['Location'])

        self.get('https://auth.sztu.edu.cn/idp/AuthnEngine')
        self.get('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain?entityId=jiaowu')
        # 构造登录
        data = {
            'j_username': school_id,
            'j_password': self.encryptByDES(password),
            'j_checkcode': '验证码',
            'op': 'login',
            'spAuthChainCode': 'cc2fdbc3599b48a69d5c82a665256b6b'
        }
        resp = self.post('https://auth.sztu.edu.cn/idp/authcenter/ActionAuthChain', data)
        resp = resp.json()
        if resp['loginFailed'] != 'false':
            # 登录失败时，明确返回False
            return False

        resp = self.post('https://auth.sztu.edu.cn/idp/AuthnEngine?'
                         'currentAuth=urn_oasis_names_tc_SAML_2.0_ac_classes_BAMUsernamePassword',
                         data=data)
        ssoURL = resp.headers['Location']
        resp = self.get(ssoURL)
        logonUrl = resp.headers['Location']

        self.session.headers['Host'] = 'jwxt.sztu.edu.cn'
        self.get(logonUrl)
        self.get('https://jwxt.sztu.edu.cn/jsxsd/framework/xsMain.htmlx')
        self.cookies = self.session.cookies.get_dict()
        self.check_login()
        # 登录成功返回True
        return True

    @staticmethod
    def encryptByDES(message, key='PassB01Il71'):
        key1 = key.encode('utf-8')[:8]
        cipher = DES.new(key=key1, mode=DES.MODE_ECB)
        encrypted_text = cipher.encrypt(pad(message, block_size=8))
        encrypted_text = base64.b64encode(encrypted_text).decode('utf-8')
        return encrypted_text

    def check_login(self):
        resp = self.get('https://jwxt.sztu.edu.cn/jsxsd/framework/xsMain.htmlx')
        self.ok = (resp.status_code == 200)

    def get(self, url):
        return self.session.get(url, timeout=10, cookies=self.cookies, verify=False, allow_redirects=False)

    def post(self, url, data):
        return self.session.post(url, timeout=10, cookies=self.cookies, verify=False, data=data, allow_redirects=False)


def get_session_with_retries(session):
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def get_pending_evaluations(auth):
    BASE_URL = "https://jwxt.sztu.edu.cn"
    find_url = BASE_URL + "/jsxsd/xspj/xspj_find.do"
    
    try:
        res_find = auth.session.get(find_url, timeout=10)
        res_find.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"访问评教入口页面失败: {e}")
        return []

    soup_find = BeautifulSoup(res_find.text, "html.parser")
    
    list_page_links = []
    for a in soup_find.find_all("a", href=True):
        if isinstance(a, Tag):
            href = a.get("href")
            if isinstance(href, str) and "xspj_list.do" in href:
                list_page_links.append(BASE_URL + href)

    all_tasks = []
    
    if list_page_links:
        print(f"发现 {len(list_page_links)} 个评教类别，正在逐个检查...")
        for list_page_url in list_page_links:
            try:
                res_list = auth.session.get(list_page_url, timeout=10)
                res_list.raise_for_status()
                soup_list = BeautifulSoup(res_list.text, "html.parser")
                for a in soup_list.find_all("a", string="评价", href=True):
                    if isinstance(a, Tag):
                        href = a.get("href")
                        if isinstance(href, str) and "xspj_edit.do" in href:
                            task_url = BASE_URL + href
                            # 存储为元组 (编辑页URL, 提交目标URL)
                            all_tasks.append((task_url, list_page_url))
            except requests.exceptions.RequestException as e:
                print(f"访问评教列表页 {list_page_url} 失败: {e}")
    else: # Fallback, unlikely to be used
        print("未发现评教类别页面，尝试直接查找评教任务...")
        # 注意：此回退逻辑无法确定正确的提交目标，可能会失败
        submit_target_url = BASE_URL + "/jsxsd/xspj/xspj_save.do" 
        for a in soup_find.find_all("a", string="评价", href=True):
            if isinstance(a, Tag):
                href = a.get("href")
                if isinstance(href, str) and "xspj_edit.do" in href:
                    task_url = BASE_URL + href
                    all_tasks.append((task_url, submit_target_url))

    return all_tasks

def get_evaluate_form(auth, edit_url):
    res = auth.session.get(edit_url, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    form = soup.find("form")
    
    if not isinstance(form, Tag):
        print("未找到评教表单，跳过该任务。")
        return None

    payload = []
    radio_groups = {}
    
    all_tags = form.find_all(['input', 'textarea', 'select'])

    for tag in all_tags:
        if not isinstance(tag, Tag): continue
        name = tag.get('name')
        if not name: continue
        
        if tag.name == 'input' and tag.get('type') == 'radio':
            if name not in radio_groups:
                radio_groups[name] = []
            radio_groups[name].append(tag)
            continue

        value = ''
        if tag.name == 'select':
            options = [o for o in tag.find_all("option") if isinstance(o, Tag)]
            valid_options = []
            for o in options:
                val = o.get("value")
                if isinstance(val, str) and val.strip():
                    valid_options.append(o)
            
            if valid_options:
                is_score = True
                for o in valid_options:
                    val = o.get("value")
                    if not (isinstance(val, str) and val.replace('.', '', 1).isdigit()):
                        is_score = False
                        break

                if is_score:
                    scores = [o.get("value") for o in valid_options if isinstance(o.get("value"), str)]
                    weights = [i + 1 for i in range(len(scores))]
                    value = random.choices(scores, weights=weights, k=1)[0]
                else:
                    random_option = random.choice(valid_options)
                    value = random_option.get("value", "")
        elif tag.name == 'textarea':
            value = tag.text or "老师讲课认真，内容充实，收获很大！"
        elif tag.name == 'input':
            if tag.get('type') == 'checkbox':
                if tag.has_attr('checked'):
                    value = tag.get('value', 'on')
            else:
                value = tag.get('value', '')
        
        payload.append((name, value))

    for name, radios in radio_groups.items():
        if radios:
            chosen_radio = random.choice(radios)
            payload.append((name, chosen_radio.get('value', '')))
    
    # URL参数补充，以防万一
    current_payload_keys = {item[0] for item in payload}
    parsed_url = urlparse(edit_url)
    query_params = parse_qs(parsed_url.query)
    for key, values in query_params.items():
        if key not in current_payload_keys:
            for v in values:
                payload.append((key, v))

    return payload

def submit_evaluation(auth, payload, submit_url, referer_url):
    BASE_URL = "https://jwxt.sztu.edu.cn"
    headers = {
        "Referer": referer_url,
        "User-Agent": "Mozilla/5.0",
        "Origin": BASE_URL,
    }
    resp = auth.session.post(submit_url, data=payload, headers=headers, timeout=15)
    return resp.text

def submit_final_evaluation(auth, list_page_url, num_tasks_in_list):
    """Performs the final 'Submit' action for a list of evaluations."""
    print(f"\n--- 正在对类别 {list_page_url.split('?')[0]} 进行最终提交 ---")
    try:
        res = auth.session.get(list_page_url, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        form = soup.find("form")
        if not isinstance(form, Tag):
            print("警告: 在列表页面上未找到最终提交的表单，跳过最终提交。")
            return
            
        payload = []
        # From the form on the list page, collect all input fields
        for tag in form.find_all("input"):
            if not isinstance(tag, Tag):
                continue
            name = tag.get("name")
            value = tag.get("value", "")
            if name and tag.get("type") not in ["submit", "button", "reset"]:
                payload.append((name, value))

        # Add the 'issavestr' parameter for each saved task, as seen in your captured data
        for _ in range(num_tasks_in_list):
            payload.append(("issavestr", "是"))
            
        # The target URL for the final submission. This is a best guess based on system patterns.
        FINAL_SUBMIT_URL = "https://jwxt.sztu.edu.cn/jsxsd/xspj/xspj_save.do"
        
        print("...发送最终提交请求...")
        result = submit_evaluation(auth, payload, submit_url=FINAL_SUBMIT_URL, referer_url=list_page_url)
        
        # The response for the final submit might be different from individual saves
        if "提交成功" in result or "评价成功" in result:
            print("✅ 最终提交成功！")
        else:
            print(f"⚠️ 最终提交可能失败，服务器响应: {result[:100].strip()}...")

    except requests.exceptions.RequestException as e:
        print(f"最终提交时发生网络错误: {e}")

if __name__ == "__main__":
    try:
        conf = ConfigParser()
        conf.read("config.txt", encoding='utf-8')
        user = conf.get('mysql', 'username')
        pwd = conf.get('mysql', 'password')
        
        print("🚀 开始自动评教...")
        a = Auth()
        a.session = get_session_with_retries(a.session)

        if not a.login(user, pwd):
            print("❌ 登录失败，请检查账号密码或网络连接。")
            sys.exit(1)
            
        print("✅ 登录成功，正在获取待评教列表...")
        tasks = get_pending_evaluations(a)
        total_tasks = len(tasks)
        
        if total_tasks == 0:
            print("🎉 未发现待评教任务，或所有任务已完成。")
            sys.exit(0)
            
        print(f"🔍 共发现 {total_tasks} 个待评教任务，将逐个保存...")

        # 1. Loop through all tasks and "save" them
        for idx, (edit_url, list_page_url) in enumerate(tasks, 1):
            print(f"\n➡️ 正在保存第 {idx}/{total_tasks} 个任务...")
            try:
                payload = get_evaluate_form(a, edit_url)
                
                if not payload:
                    print("表单采集失败，跳过。")
                    continue
                    
                time.sleep(random.uniform(2, 5))
                
                result = submit_evaluation(a, payload, submit_url=list_page_url, referer_url=edit_url)
                
                if "暂存成功" in result or "已保存" in result or "评价成功" in result:
                    print(f"✅ 保存成功!")
                else:
                    print(f"✅ 保存请求已发送 (服务器无明确回执)。")

            except requests.exceptions.RequestException as e:
                print(f"处理保存任务时发生网络错误: {e}")
                print("等待5秒后继续...")
                time.sleep(5)

        # 2. After ALL tasks are saved, perform ONE final submit
        print("\n--- 所有任务已保存完毕，正在进行最终提交 ---")
        # Use the list_page_url from the last task for the final submission page
        final_submit_list_page_url = tasks[-1][1]
        submit_final_evaluation(a, final_submit_list_page_url, total_tasks)
                 
        print("\n🎉 全部评教任务处理完毕！")
    except Exception as e:
        print(f"\n💥 发生异常: {str(e)}")
        traceback.print_exc() 