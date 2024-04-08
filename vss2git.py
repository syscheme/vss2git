# encoding: UTF-8

from __future__ import division
from abc import abstractmethod
import traceback, tempfile
import re
from datetime import datetime
import zlib
import os, sys, subprocess
import pathlib, pickle, bz2

SS_EXE = os.path.join(os.path.dirname(__file__), 'SS.EXE')
VERSION_HDR='*****************  Version '
HEADER_LEADING_STARS='*****'
VERBS_IGNORE_ON_CHILD='labeled|added|deleted|destroyed|recovered|purged'.split('|')
CMD_PROMPT='cmd> '

def exec_cmd(cmd): 
    print('%s%s'%(CMD_PROMPT, cmd))
    # os.system(cmd)

def exec_git(subcmd):  exec_cmd('git %s'%subcmd)
def exec_ss(subcmd):   exec_cmd('%s %s'%(SS_EXE, subcmd))

# ---------------------------------------
def tree_files(tree_top='$/') :
    files = []
    
    # os.system('SS.EXE Dir -R -E $/')
    child = subprocess.Popen((SS_EXE + ' Dir -R -E ' +tree_top).split(' '), # 命令及其参数
                            stdin=subprocess.PIPE,      # 标准输入（可向其写入）
                            stdout=subprocess.PIPE,     # 标准输出（可从中读取）
                            stderr=subprocess.PIPE,     # 标准错误输出（可从中读取）
                            text=True                   # 设置文本模式，适用于Python 3.7+
                            )
    # # 向子进程的stdin写入一些数据
    # input_data = "This is some test data containing keyword and anotherkeyword"
    # child.stdin.write(input_data)
    # child.stdin.flush()  # 确保数据立即发送到子进程

    # 从子进程的stdout和stderr中读取数据
    stdout_output, stderr_output = child.communicate()
    # 检查子进程的退出状态码
    if 0 != child.returncode :
        print("\nExitCode(%s) %s" % (child.returncode, stderr_output))
    child.stdin.close()
    child.stdout.close()
    child.stderr.close()

    # print("Standard Output:\n", stdout_output)
    for line in stdout_output.split('\n') :
        line = line.strip()
        if len(line) <=0: continue
        if '$' == line[0] :
            if ':' == line[-1]:
                tree_top = line[:-1]
                if '/' != tree_top[-1] : tree_top +='/'
            else :
                files.append(tree_top + line[1:] +'/') # subdir
            continue

        files.append(tree_top + line)

    if len(files)>0 and  'item(s)' in files[-1] :
        del files[-1] 

    files.sort()
    return files

# ---------------------------------------
def history_of_file(filepath, only_on_self=False) :
    fn_ret, file_hist = '', [] # the return value
    # os.system('SS.EXE Dir -R -E $/')
    child = subprocess.Popen((SS_EXE + ' History '+filepath).split(' '), # 命令及其参数
                            stdin=subprocess.PIPE,      # 标准输入（可向其写入）
                            stdout=subprocess.PIPE,     # 标准输出（可从中读取）
                            stderr=subprocess.PIPE,     # 标准错误输出（可从中读取）
                            text=True                   # 设置文本模式，适用于Python 3.7+
                            )
    stdout_output, stderr_output = child.communicate()

    # 检查子进程的退出状态码
    if 0 != child.returncode :
        print("\nExitCode(%s) %s" % (child.returncode, stderr_output))
    child.stdin.close()
    child.stdout.close()
    child.stderr.close()

    current={}
    head_ln =''
    # print(stdout_output)
    for line in stdout_output.split('\n') :
        line = line.strip()
        if len(line) <=0: continue

        if HEADER_LEADING_STARS == line[:len(HEADER_LEADING_STARS)] : # new block starts
            others = current.pop('others','')
            verb = current.pop('verb', None)
            strdt =current.pop('asof','')
            author=current.pop('author','')
            if verb : 
                current = {'asof':strdt, 'author':author, 'verb':verb, **current, 'header':head_ln }
                if only_on_self and VERSION_HDR != head_ln[:len(VERSION_HDR)] and verb in VERBS_IGNORE_ON_CHILD :
                    # print('ignored activity on child: %s %s others: %s'%(head_ln, current, others)) # TESTCODE
                    pass
                else :
                    str2crc = '%s/%s@%s' %(author, verb,':'.join(strdt.split(':')[:-1]))

                    if 'labeled' == verb : str2crc += '%s}}%s' %(current.get('label_title'), current.get('comment'))
                    elif 'checkedin' == verb : str2crc += '%s' %(current.get('comment'))

                    current['uniq'] = '%08X' % zlib.crc32(str2crc.encode('utf-8'))
                    
                    if len(others) >0 : current['others'] = others
                    file_hist.append(current)

                current={}
                # if len(journal)>30: break # TESTCODE
            elif len(head_ln) >0 :
                print('NOT UNDDERSTAND: %s %s others: %s'%(head_ln, current, others))

            head_ln = line
            current={'others':[]}

            if VERSION_HDR == head_ln[:len(VERSION_HDR)] :
                current['version'] = head_ln[len(VERSION_HDR):].split(' ')[0]

            continue

        elif len(head_ln) <=0 :
            if len(fn_ret) <=0 :
                # History of $/CTFLib/V2.0/CTFTest/ctfTest.c ...
                m = re.match(r'History of ([^ ]*) ...', line)
                if m :
                    fn_ret = m.group(1).strip()
                    if '/' == filepath[-1] and '/' != fn_ret[-1] : fn_ret+='/'

            head_ln=''
            continue

        # parse a line

        # Label: "V9.67.6.0"
        m = re.match(r'Label: "([^"]*)"', line)
        if m :
            current['verb'] = 'labeled'
            current['label_title'] = m.group(1)
            continue

        # User: Gary.thomas     Date: 19/09/04   Time:  7:37
        m = re.match(r'User: (.*)Date: (.*)Time: (.*)', line)
        if m :
            current['author']  = m.group(1).strip()
            dtRecent = datetime.strptime(m.group(2).strip()+'T'+m.group(3).strip(), '%y/%m/%dT%H:%M')
            dtRecent = dtRecent.replace(second=59) # .99)
            current['asof'] = dtRecent.strftime('%Y-%m-%dT%H:%M:%S') 
            continue

        # Label comment: MCDriver-V9.67.6.0
        m = re.match(r'Label comment:(.*)', line)
        if m :
            current['comment'] = m.group(1).strip()
            continue

        # Checked in $/MCDriver-Topology/Version_inc
        m = re.match(r'Checked in (.*)', line)
        if m :
            fn_loc = m.group(1).strip()
            current['verb'] = 'checkedin'
            current['fn_loc'] = fn_loc
            continue

        # Comment: Add UHD
        m = re.match(r'Comment:(.*)', line)
        if m :
            current['comment'] = m.group(1).strip()
            continue

        # SeaResource.h added | $VstrmSDK added
        m = re.match(r'(.+) (added|deleted|destroyed|recovered|purged)', line)
        if m :
            fn_loc = m.group(1).strip()
            if '$' == fn_loc[0] : fn_loc = fn_loc[1:] +'/'
            if VERSION_HDR == head_ln[:len(VERSION_HDR)] and '/' == filepath[-1]:
                fn_loc = filepath+fn_loc

            current['verb'] = m.group(2).strip().lower()
            current['filepath'] = fn_loc
            continue

        # $V3.0-Special renamed to $V3.2
        m = re.match(r'([^ ]+) renamed to (.+)', line)
        if m :
            fn_loc = m.group(1).strip()
            if '$' == fn_loc[0] : fn_loc = fn_loc[1:] +'/'
            if VERSION_HDR == head_ln[:len(VERSION_HDR)] and '/' == filepath[-1]:
                fn_loc = filepath+fn_loc

            current['verb'] = 'renamed'
            current['filepath'] = fn_loc
            fn_loc = m.group(2).strip()
            if '$' == fn_loc[0] : fn_loc = fn_loc[1:] +'/'
            current['renamed_to'] = fn_loc
            continue

        # Created
        if 'Created' == line and '1' == current.get('version') :
            current['verb'] = 'created'

        if line in ['Labeled'] :
            continue # known line but useless
    
    file_hist.reverse()
    return fn_ret, file_hist

'''
# ---------------------------------------
def parse_jounal(fn_journal) : # file output by cmd: SS.EXE History -O@CTFLib_journal.txt $/
    journal =[]
    dtRecent,dtLast = None, None
    with open(fn_journal, 'r') as fjn :
        current={}
        head_ln=''
        for line in fjn.readlines() :
            line = line.split('\r')[0].split('\n')[0]
            # print(line)

            if HEADER_LEADING_STARS == line[:len(HEADER_LEADING_STARS)] : # new block starts
                others = current.pop('others','')
                verb = current.pop('verb', None)
                strdt =current.pop('asof','')
                author=current.pop('author','')
                if verb: 
                    current = {'asof':strdt, 'author':author, 'verb':verb, **current, 'header':head_ln}
                    str2crc = '%s/%s@%s' %(author, verb,':'.join(strdt.split(':')[:-1]))

                    if 'labeled' == verb : str2crc += '%s}}%s' %(current.get('label_title'), current.get('comment'))
                    elif 'checkedin' == verb : str2crc += '%s' %(current.get('comment'))

                    current['uniq'] = '%08X' % zlib.crc32(str2crc.encode('utf-8'))
                  
                    if len(others) >0 : current['others'] = others
                    journal.append(current)
                    # if len(journal)>30: break # TESTCODE
                elif len(head_ln) >0 :
                    print('NOT UNDDERSTAND: %s %s others: %s'%(head_ln, current, others))

                head_ln = line
                current={'others':[]}
                continue

            if len(head_ln) <=0 : # or VERSION_HDR == head_ln[:len(VERSION_HDR)] :
                head_ln=''
                continue

            # parse the line

            # Version 67
            m = re.match(r'Version ([0-9]*)', line)
            if m :
                current['version'] = m.group(1)
                continue

            # Label: "V9.67.6.0"
            m = re.match(r'Label: "([^"]*)"', line)
            if m :
                current['verb'] = 'labeled'
                current['label_title'] = m.group(1)
                continue

            # User: Gary.thomas     Date: 19/09/04   Time:  7:37
            m = re.match(r'User: (.*)Date: (.*)Time: (.*)', line)
            if m :
                current['author']     = m.group(1).strip()
                dtRecent = datetime.strptime(m.group(2).strip()+'T'+m.group(3).strip(), '%y/%m/%dT%H:%M')
                dtRecent = dtRecent.replace(second=59) # .99)
                current['asof'] = dtRecent.strftime('%Y-%m-%dT%H:%M:%S') 
                continue

            # Label comment: MCDriver-V9.67.6.0
            m = re.match(r'Label comment:(.*)', line)
            if m :
                current['comment'] = m.group(1).strip()
                continue

            # Checked in $/MCDriver-Topology/Version_inc
            m = re.match(r'Checked in (.*)', line)
            if m :
                fn_path = m.group(1).strip() + '/'+ head_ln[6:-6].strip()
                current['verb'] = 'checkedin'
                current['filepath'] = fn_path
                continue

            # Comment: Add UHD
            m = re.match(r'Comment:(.*)', line)
            if m :
                current['comment'] = m.group(1).strip()
                continue

            # SeaResource.h added | $VstrmSDK added
            m = re.match(r'(.+) (added|deleted|destroyed|recovered|purged)', line)
            if m :
                fn_path = m.group(1).strip()
                if '$' == fn_path[0] : fn_path = fn_path[1:] +'/'
                if VERSION_HDR == head_ln[:len(VERSION_HDR)] :
                    fn_path = '$/' + fn_path
                else :
                    fn_path = '$/???/' + head_ln[6:-6].strip() +'/' + fn_path
                current['verb'] = m.group(2).strip().lower()
                current['filepath'] = fn_path
                continue

            # $V3.0-Special renamed to $V3.2
            m = re.match(r'([^ ]+) renamed to (.+)', line)
            if m :
                fn_path = m.group(1).strip()
                if VERSION_HDR == head_ln[:len(VERSION_HDR)] :
                    parent_path = '$/'
                else :
                    parent_path = '$/???/' + head_ln[6:-6].strip() +'/'
                if '$' == fn_path[0] : fn_path = fn_path[1:] +'/'
                current['verb'] = 'renamed'
                current['filepath'] = parent_path + fn_path
                fn_path = m.group(2).strip()
                if '$' == fn_path[0] : fn_path = fn_path[1:] +'/'
                current['renamed_to'] = parent_path + fn_path
                continue

            # Created
            if 'Created' == line and '1' == current.get('version') :
                fn_path = '$/???/'+ head_ln[6:-6].strip() +'/'
                current['verb'] = 'created'
                current['filepath'] = fn_path

            if line in ['Labeled'] :
                continue # known line but useless

            if len(line) >0: current['others'].append(line)

    journal.reverse()
    return journal

# ---------------------------------------
def associateActivity(filepath, **kwargs) : 
    return associateActivity_bySnapshot(filepath, **kwargs) 
    # return associateActivity_byFinal(filepath, **kwargs)
# ---------------------------------------
FILES_FINAL = None
def associateActivity_byFinal(filepath, **kwargs) :
    global FILES_FINAL # nonlocal
    if not isinstance(FILES_FINAL, dict) or len(FILES_FINAL) <=0:
        FILES_FINAL={}
        # files = tree_files()
        # files.sort()
        for fn in tree_files() :
            fn =fn.replace('//','/')
            key = fn.split('/')
            key.reverse()
            key = '/'.join(key)
            FILES_FINAL[key] = { 'path': fn }

    ret_files=[]
    if '$/???/' != filepath[:len('$/???/')] :
        hit = (filepath, kwargs.get('version',''))
        ret_files.append(hit)
    else :
        asof = kwargs.get('asof')
        uniq = kwargs.get('uniq')
        key = filepath[6:].split('/')
        key.reverse()
        key = '/'.join(key)
        candicates = list(filter(lambda x : x>=key and x <(key+'}'), FILES_FINAL.keys()))
        for ck in candicates :
            if len(FILES_FINAL[ck].get('hist',[])) <=0 :
                fn_candi = FILES_FINAL[ck]['path']
                fn, file_hist = history_of_file(fn_candi)
                if fn != fn_candi or len(file_hist) <=0:
                    print('candidate[%s] for %s not survived' % (fn_candi, filepath))
                    continue
                FILES_FINAL[ck]['hist'] =file_hist

            file_hist = FILES_FINAL[ck]['hist']
            for h in file_hist :
                # TODO: if asof < h.get('asof') : break
                # TODO: if asof == h.get('asof') and uniq ==h.get('uniq') :
                if uniq ==h.get('uniq') :
                    hit = (FILES_FINAL[ck]['path'], h.get('version'))
                    ret_files.append(hit)
                    print('%s hit %s' % (filepath, hit))
                    break
    
    return ret_files

# ---------------------------------------
FILES_SNAPSHOT = {}
def associateActivity_bySnapshot(filepath, verb, asof, **kwargs) :
    global FILES_SNAPSHOT # nonlocal

    uniq = kwargs.get('uniq', '')
    ret_files=[]
    if '$/???/' != filepath[:len('$/???/')] :
        hit = (filepath, kwargs.get('version',''))
        ret_files.append(hit)
        key = filepath.split('/')
        key.reverse()
        key = '/'.join(key)

        if verb in ['deleted'] :
           if key in FILES_SNAPSHOT : 
               del FILES_SNAPSHOT[key]
        elif key not in FILES_SNAPSHOT or 'hist' not in FILES_SNAPSHOT[key]:
            fn, file_hist = history_of_file(filepath)
            if not fn and verb in ['added'] :
                fn =filepath
            FILES_SNAPSHOT[key] = { 'path': fn, 'hist' : file_hist }

        if verb in ['renamed', 'shared'] :
            new_key = kwargs.get('renamed_to','')
            FILES_SNAPSHOT[new_key] = FILES_SNAPSHOT[key]
            del FILES_SNAPSHOT[key]
            
        if verb in ['shared'] :
            new_key = kwargs.get('shared_to','')
            FILES_SNAPSHOT[new_key] = FILES_SNAPSHOT[key]
    else :
        key = filepath[6:].split('/')
        key.reverse()
        key = '/'.join(key)
        candicates = list(filter(lambda x : x>=key and x <(key+'}'), FILES_SNAPSHOT.keys()))

        if verb in ['added'] :
            candidir = list(filter(lambda x: '/'==x[0], FILES_SNAPSHOT.keys()))
            candicates += [ (key+x) for x in candidir ] + [ key+'/$' ]

        for ck in candicates :
            node = FILES_SNAPSHOT.get(ck,{})
            if len(node.get('hist',[])) <=0 :
                fn_candi = node.get('path')
                if not fn_candi:
                    stkns = ck.split('/')
                    stkns.reverse()
                    fn_candi = '/'.join(stkns)
                fn, file_hist = history_of_file(fn_candi)
                if fn != fn_candi or len(file_hist) <=0:
                    print('candidate[%s] for %s not survived' % (fn_candi, filepath))
                    continue
                FILES_SNAPSHOT[ck]= {'path':fn, 'hist':file_hist}

            file_hist = FILES_SNAPSHOT[ck]['hist']
            for h in file_hist :
                # TODO: if asof < h.get('asof') : break
                # TODO: if asof == h.get('asof') and uniq ==h.get('uniq') :
                if uniq ==h.get('uniq') :
                    hit = (FILES_SNAPSHOT[ck]['path'], h.get('version'))
                    ret_files.append(hit)
                    print('%s hit %s' % (filepath, hit))
                    break

            if len(ret_files) <=0 and verb in ['added'] :
                if key+'/$' in FILES_SNAPSHOT :
                    n = ('$/'+filepath[6:], kwargs.get('version'))
                    print('added %s treated as %s' % (filepath, n))
                    ret_files.append(n)
    
    print('assocated %s: %s' % (filepath, ret_files))
    return ret_files
'''

# =======================================
TREE_SNAPSHOT = {}
TREE_FINAL = {}

def buildup_history(journal=None, **kwargs) :
    global TREE_FINAL # nonlocal

    journal_merged =[]
    fn_cache='d:\\temp\\hist.bz2pkl'
    if not isinstance(TREE_FINAL, dict) or len(TREE_FINAL) <=0:
        if os.path.exists(fn_cache) :
            with bz2.open(fn_cache, 'rb') as f:
                TREE_FINAL = pickle.load(f)
        if not isinstance(TREE_FINAL, dict) or len(TREE_FINAL) <=0:
            for fn in tree_files() :
                path, hist = history_of_file(fn, only_on_self=True)
                TREE_FINAL[fn] = {
                    'path': path,
                    # 'stepNext': 0,
                    'hist': hist
                    }
            with bz2.open(fn_cache, 'wb') as f:
                pickle.dump(TREE_FINAL, f)
        
    last_asof=''
    while True :
        nexts = []
        min_next_next = '9999-12-31T23:59:59'
        for path,v in TREE_FINAL.items() :
            # stepNext = v.get('stepNext', -1)
            # hist = v.get('hist', [])
            # if stepNext >=0 and stepNext < len(hist) :
            #     s = hist[stepNext]
            #     asof = s.get('asof')
            #     if stepNext < len(hist)-1 :
            #         min_next_next = min(min_next_next, hist[stepNext+1].get('asof', min_next_next))
            #     nexts.append((asof, path))
            if 'hist' in v and isinstance(v['hist'], list) and len(v['hist']) >0:
                s = v['hist'][0]
                asof = s.get('asof')
                nexts.append((asof, path))
                if len(v['hist']) >1 and v['hist'][1].get('asof', min_next_next) < min_next_next :
                    min_next_next = v['hist'][1].get('asof', min_next_next)

        if len(nexts) <=0: # Done
            break

        nexts = list(filter(lambda x: x[0] <=min_next_next, nexts))

        nexts.sort(key=lambda x: '%30s:%s' %(x[0],x[1]))

        step = None
        for asof, path in nexts :
            if isinstance(step, dict) and 'verb' in step : # all invalid steps have been set to None
                journal_merged.append(step)
                print('buildup_history() merged step: %s' %step) # TESTCODE
                # last_asof = max(last_asof, step.get('asof', ''))
                step=None

            # filenode = TREE_FINAL[path]
            # stepNext = filenode.get('stepNext')
            # step = filenode.get('hist')[stepNext]
            # filenode['stepNext'] = 1+stepNext
            step = TREE_FINAL[path]['hist'].pop(0)

            if not isinstance(step, dict) : continue
            filepath = step.get('filepath', path)
            step['filepath'] =filepath

            asof = step.get('asof')
            author = step.get('author')
            verb = step.get('verb')
            uniq = step.get('uniq')
            if verb in ['created', 'added'] : verb= 'added'
            if verb in ['destroyed', 'deleted'] : verb= 'deleted'
            step['verb'] =verb

            head_ln = step.get('header','')
            if VERSION_HDR != head_ln[:len(VERSION_HDR)] and verb in VERBS_IGNORE_ON_CHILD :
                step = None # ignore those activity not directly on self but on child
                continue 

            print('buildup_history() stepped %s> %s' %(filepath, step)) # TESTCODE

            '''
            if verb in ['added'] :
                child = step.get('filepath')
                if not child in TREE_FINAL :
                    child, hist = history_of_file(child)
                    if isinstance(hist) and len(hist) >0 :
                        TREE_FINAL[fn] = {
                            'path': path,
                            'stepNext': 0,
                            'hist': hist
                            }
                        break # to refresh nexts
            '''

        if isinstance(step, dict) and 'verb' in step : # all invalid steps have been set to None
            journal_merged.append(step)
            print('buildup_history() merged step: %s' %step) # TESTCODE
            # last_asof = max(last_asof, step.get('asof', ''))
            step=None
            
    return journal_merged

# ---------------------------------------
def associateActivity(filepath, **kwargs) :
    return [(filepath, kwargs.get('version',''))]

########################################################################
if __name__ == '__main__':

    os.environ['SSDIR']  = 'D:/temp/vss/CTFLib'
    os.environ['SSUSER'] = 'build'
    os.environ['SSPWD']  = 'nightly'

    local_top = 'd:\\temp\\vss2git_top'
    local_top = os.path.join(local_top, os.path.basename(os.environ['SSDIR']))

    exec_cmd('rd /s/q %s' %(local_top))
    exec_cmd('if not exist "%s" mkdir "%s"' %(local_top, local_top))
    if not os.path.isdir(local_top) :
        pathlib.Path(local_top).mkdir(parents=True, exist_ok=True) 

    sys.path.insert(0, os.path.dirname(__file__))
    fn_journal = os.path.join(os.getcwd(), 'CTFLib_journal.txt') # SS.EXE History -O@CTFLib_journal.txt $/
    os.chdir(local_top)
    exec_cmd('cd /d %s' %(local_top))
    exec_git('init')
    exec_git('config --global user.name  "vss2git"')
    exec_git('config --global user.email "vss2git@syscheme.com"')

    # files = tree_files()
    # print('\n'.join(files))
    # exit(0)
    # _, hist = history_of_file('$/CTFLib/V2.0/CTFLib2.sln') # ever renamed
    # _, hist = history_of_file('$/CTFLib/V3.0-SEAC/CTFTest/ctfTest3.0.suo') # ever deleted
    # _, hist = history_of_file('$/CTFLib/build/buildbatch.txt') # long hist
    # _, hist = history_of_file('$/CTFLib/build/') # long hist
    # print('\n'*2+'>'*40)
    # print('\n'.join([str(i) for i in hist]))
    # exit(0)

    journal = buildup_history()
    # exit(0)

    last_author, author, last_verb, verb, last_uniq =None, None, None, None, None
    bth_files, git_comment = [], ''
    last_tagged = None
    def __commit(label_title=None, label_commit=None) :
        global bth_files, git_comment # nonlocal
        if len(bth_files) >0 : 
            gitcmd = 'commit -m "%s"' % (git_comment)
            exec_git(gitcmd)
        if isinstance(label_title, str) and len(label_title) >0 :
            global last_tagged
            tag = label_title.replace(' ','_') # TODO format
            if last_tagged != tag : 
                gitcmd = 'tag "%s" -m "%s"' % (tag, label_commit)
                exec_git(gitcmd)
            last_tagged = tag

        bth_files, git_comment = [], ''

    # journal = list(filter(lambda x: 'buildbatch.txt' in x.get('filepath', ''), journal)) # TESTCODE
    def __to_localfile(filepath) :
        localfn = filepath
        if '$/' == localfn[:2] : localfn = localfn[2:]
        if '/' == localfn[0]   : localfn = localfn[1:]
        localfn = './'+localfn
        subdir = os.path.dirname(localfn) if '/'!=localfn[-1] else localfn
        subdir = os.path.relpath(subdir)
        exec_cmd('if not exist "%s" mkdir "%s"' %(subdir, subdir)) # TESTCODE
        if not os.path.isdir(subdir) : 
            pathlib.Path(os.path.relpath(subdir)).mkdir(parents=True, exist_ok=True) 
        return os.path.relpath(localfn)

    for step in journal :
        # print(step) # TESTCODE
        author = step.get('author')
        verb = step.get('verb')
        uniq = step.get('uniq')
        if verb in ['created', 'added'] : verb= 'added'
        if verb in ['destroyed', 'deleted'] : verb= 'deleted'
        step['verb'] =verb

        if last_author != author or last_verb != verb or (last_verb in ['checkedin'] and last_uniq != uniq): # or uniqkey changed
            __commit()

        last_author, last_verb, last_uniq = author, verb, uniq
        filepath = step.get('filepath')

        if 'labeled' == verb :
            comment = step.get('comment')
            comment = '%s %s tagged: %s' %(step.get('asof',''), author, comment)
            __commit(label_title=step.get('label_title'), label_commit=comment)
            continue

        sscmd, gitcmd = '',''
        git_comment = '%s %s %s' % (step.get('asof'), author, verb)
        if 'added' == verb :
            if '/' == filepath[-1] : continue
            step['filepath'] = filepath
            files_to_pull = associateActivity(**step)
            for sspath, ssver in files_to_pull :
                if '/' == sspath[-1] : continue  # ignore subdirs
                localfn = __to_localfile(sspath[2:])
                sscmd  = 'GET %s -V%s > %s' % (sspath, ssver, localfn)
                exec_ss(sscmd)
                gitcmd = 'add -f %s' % (localfn)
                bth_files.append(localfn)
                exec_git(gitcmd)
            continue
    
        '''
        if 'deleted' == verb :
            # if '/' == filepath[-1] : continue # ignore subdirs

            files_to_pull = associateActivity(**step)
            for sspath, ssver in files_to_pull :
                localfn = __to_localfile(sspath[2:])
                gitcmd = 'rm %s' % (localfn)
                bth_files.append(localfn)
                exec_git(gitcmd)
            continue

        if 'renamed' == verb :
            renamed_to = step.get('renamed_to')

            files_to_pull = associateActivity(**step)
            for sspath, ssver in files_to_pull :
                localfn = __to_localfile(sspath[2:])
                local_renamed_to = __to_localfile(renamed_to)
                gitcmd = 'mv %s %s' % (localfn, local_renamed_to)
                bth_files.append(localfn)
                exec_git(gitcmd)

            continue
        '''

        if 'checkedin' == verb :
            git_comment += ': %s'%step.get('comment')
            files_to_pull = associateActivity(**step)
            for sspath, ssver in files_to_pull :
                localfn = __to_localfile(sspath[2:])
                if '/' == sspath[-1] : continue  # ignore subdirs
                sscmd  = 'GET %s -V%s > %s' % (sspath, ssver, localfn)
                exec_ss(sscmd)
                gitcmd = 'add -f %s' % localfn
                bth_files.append(localfn)
                exec_git(gitcmd)
            continue

        print('NOT-YET: %s'%step)


    # print('\n'*2+'>'*40)
    # print('\n'.join([str(i) for i in journal]))

'''
download git for windows: https://git-scm.com/download/win

https://learn.microsoft.com/en-us/previous-versions/7174xsc2(v=vs.80)
https://learn.microsoft.com/en-us/previous-versions/hsxzf2az(v=vs.80)
https://svn.ssec.wisc.edu/repos/APSPS/trunk/SPS/Installer/AntInstaller-beta0.8/web/manual1.6.2/manual/OptionalTasks/vss.html#vsshistory

All
-# Option (Command Line)
Specifies the number of entries for the History command to display for a file or project.
-? Option (Command Line)
Gets Help for the selected command.
-B Option (Command Line)
Specifies if files are binary or text for the Properties, Add, and Filetype commands. For the History and Diff commands, the -B option specifies a brief format. For the Merge command, this option specifies the base version for the destination project.
-C Option (Command Line)
Specifies a comment for a command.
-D Option (Command Line)
Controls how Visual SourceSafe displays differences.
-E Option (Command Line)
Produces an extended display for the Dir command, including checkout information for files. For the Share command, this option specifies a share and branch operation. When used with the Add, Properties, and Filetype commands, the option specifies the file encoding.
-F Option (Command Line)
Enables a display for files only, with no projects.
-G Option (Command Line)
Sets options for a retrieved working copy.
-H Option (Command Line)
Requests Help for the selected command.
-I Option (Command Line)
Indicates what factors Visual SourceSafe should ignore when comparing two files.
-K Option (Command Line)
Specifies if a file remains checked out after you check it in.
-L Option (Command Line)
Specifies labels for files or projects for many commands. For the Checkout command, this option enables or disables the check out local version feature.
-M Option (Command Line)
Disables exclusive checkouts for an individual file.
-N Option (Command Line)
Specifies the file naming conventions for a command.
-O Option (Command Line)
Controls the output from commands that might display large amounts of information.
-P Option (Command Line)
Specifies a project to use with a command.
-Q Option (Command Line)
Suppresses output for a command line command.
-R Option (Command Line)
Makes commands that operate on projects recursive to subprojects.
-S Option (Command Line)
Overrides the Smart_Mode initialization variable for a particular command.
-U Option (Command Line)
Displays user information about a file or project.
-V Option (Command Line)
Indicates the version of a file or project (item).
-W Option (Command Line)
Indicates if working copies are to be read/write or read-only.
-Y Option (Command Line)
Specifies a user name or user name and password.


https://learn.microsoft.com/en-us/previous-versions/003ssz4z(v=vs.80)
ss History <items> [-B] [-D] [-F-] [-H] [-I-] [-L] [-N] [-O] [-R] [-U<username>] [-V] [-Y] [-#] [-?]
ss Diff <files> [-B][-D][-H][-I][-I-][-N][-O][-V][-Y][-?]
ss Locate <items> [-H] [-I-] [-N] [-O] [-Y] [-?] # Searches Visual SourceSafe projects for the specified files or projects
ss Paths <files> [-N] [-O] [-Y] # Shows all share links for files that have been branched. 
ss Workfold [<project>] [<folder>] [-H] [-?] # Sets the working folder.
ss Get <items> [-G] [-H] [-I-] [-N] [-O] [-R] [-V] [-W] [-Y] [-?]
Retrieves a read-only copy of the file Test.c that is labeled Final: ss Get -VlFinal TEST.C

D:/wkspaces/vss2git>set SSDIR=D:/temp/vss/CTFLib
D:/wkspaces/vss2git>set SSUSER=build
D:/wkspaces/vss2git>set SSPWD=nightly
D:/wkspaces/vss2git>SS.EXE Dir -R -E -Ybuild,nightly $/
...
D:/wkspaces/vss2git>SS.EXE History -Ybuild,nightly $/MCDriver-Topology/Version_inc/version.h
Username: ahs
Password:
User "ahs" not found
Username: build
Password: *******
History of $/MCDriver-Topology/Version_inc/version.h ...

**********************
Label: "V10.69.2.0"
User: Gary.thomas     Date: 19/05/21   Time:  7:28
Labeled
Label comment: Added UHD support

*****************  Version 2   *****************
User: Gary.thomas     Date: 19/05/21   Time:  7:26
Checked in $/MCDriver-Topology/Version_inc
Comment: Add UHD

**********************
Label: "V10.68.1.0"
User: Gary.thomas     Date: 19/02/13   Time:  8:43
Labeled
Label comment: Version 10.68.1.0 - Release Candidate 1

*****************  Version 1   *****************
User: Gary.thomas     Date: 19/02/13   Time:  8:31
Created
Comment:

D:/wkspaces/vss2git>SS.EXE GET -Ybuild,nightly /$/$branch/* -R -GWR -i-
sCommand.Format(FormatStr("%s Get /"%s/" -V%d %s -GL/"%s/" >> %s",
		ss_exe,
		szVssFile,
		nVssFileVersion,
		config::szVssGetQuestionAnswer,
		sTo,
		szOutputFile));
'''


