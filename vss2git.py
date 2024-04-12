# encoding: UTF-8

from __future__ import division
from abc import abstractmethod
import traceback, tempfile
import re
from datetime import datetime
import zlib
import os, sys, subprocess
import pathlib, pickle, bz2

SS_EXE = os.path.join(os.path.dirname(__file__), 'bin', 'SS.EXE')
VERSION_HDR='*****************  Version '
HEADER_LEADING_STARS='*****'
VERBS_IGNORE_ON_CHILD='labeled|added|deleted|destroyed|recovered|purged'.split('|')

CMD_PROMPT='SCRIPT> '

def exec_cmd(cmd): 
    print('%s%s'%(CMD_PROMPT, cmd))
    # os.system(cmd)

def exec_git(subcmd):  exec_cmd('git %s'%subcmd)
def exec_ss(subcmd):   exec_cmd('%s %s'%(SS_EXE, subcmd))

def debug(msg): 
    print('DEBUG> %s'%msg)

# ---------------------------------------
def tree_files(tree_top='$/') :
    files = []
    
    # os.system('SS.EXE Dir -R -E $/')
    child = subprocess.Popen((SS_EXE + ' DIR -R -E').split(' ') +[tree_top], # 命令及其参数
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
        debug("SS-DIR err(%s) %s" % (child.returncode, stderr_output))
    child.stdin.close()
    child.stdout.close()
    child.stderr.close()

    # debug("Standard Output:\n", stdout_output)
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
    child = subprocess.Popen((SS_EXE + ' History').split(' ') +[filepath], # 命令及其参数
                            stdin=subprocess.PIPE,      # 标准输入（可向其写入）
                            stdout=subprocess.PIPE,     # 标准输出（可从中读取）
                            stderr=subprocess.PIPE,     # 标准错误输出（可从中读取）
                            text=True                   # 设置文本模式，适用于Python 3.7+
                            )
    stdout_output, stderr_output = child.communicate()

    # 检查子进程的退出状态码
    if 0 != child.returncode :
        debug("SS-History err(%s) %s" % (child.returncode, stderr_output))
    child.stdin.close()
    child.stdout.close()
    child.stderr.close()

    current={}
    head_ln =''
    debug(stdout_output)

    selfAsDir = ('/' == filepath[-1])

    def __flush_current() :
        nonlocal current, file_hist, head_ln
        others = current.pop('others','')
        verb = current.pop('verb', None)
        strdt =current.pop('asof','')
        author=current.pop('author','')
        if verb : 
            current = {'asof':strdt, 'author':author, 'verb':verb, **current, 'header':head_ln }
            if only_on_self and VERSION_HDR != head_ln[:len(VERSION_HDR)] : # and verb in VERBS_IGNORE_ON_CHILD :
                debug('ignored activity on non-self: %s %s others: %s'%(head_ln, current, others)) # TESTCODE
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
            debug('NOT UNDDERSTAND: %s %s others: %s'%(head_ln, current, others))

    child_focus=None
    for line in stdout_output.split('\n') :
        line = line.strip()
        if len(line) <=0: continue

        if HEADER_LEADING_STARS == line[:len(HEADER_LEADING_STARS)] : # new block starts
            __flush_current()
            head_ln = line
            child_focus=None
            current={'others':[]}
            if len(fn_ret) >1 :
                selfAsDir = ('/' == fn_ret[-1])
                current['filepath'] = fn_ret

            if VERSION_HDR == head_ln[:len(VERSION_HDR)] :
                current['version'] = head_ln[len(VERSION_HDR):].split(' ')[0]
            else :
                m = re.match(r'\*\*\*\*\*  (.+)  \*\*\*\*\*', line)
                if m : child_focus = m.group(1).strip()

            continue

        elif len(head_ln) <=0 :
            if len(fn_ret) <=0 :
                # SS.EXE History with no option -R
                # History of $/CTFLib/V2.0/CTFTest/ctfTest.c ...
                m = re.match(r'History of ([^ ]*) ...', line)
                if m :
                    fn_ret = m.group(1).strip()
                    if '/' == filepath[-1] and '/' != fn_ret[-1] : fn_ret+='/'

            if len(fn_ret) <=0 :
                # if apply option -R on SS.EXE History <folder>, the output becomes:
                # Building list for $/CTFLib/build...
                m = re.match(r'Building list for .*', line)
                if m : # this must be a dir
                    fn_ret = filepath
                    if '/' != fn_ret[-1] : fn_ret+='/'
            
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
            current['where'] = fn_loc
            if selfAsDir and child_focus: 
                current['child'] = child_focus
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
            current['verb'] = m.group(2).strip().lower()

            if selfAsDir :
                current['child' if VERSION_HDR == head_ln[:len(VERSION_HDR)] else 'offspring' ] = fn_loc
            else :
                debug('NotYetCovered: %s'%line)

            continue

        # $V3.0-Special renamed to $V3.2
        m = re.match(r'([^ ]+) renamed to (.+)', line)
        if m :
            fn_loc = m.group(1).strip()
            if '$' == fn_loc[0] : fn_loc = fn_loc[1:] +'/'
            current['verb'] = 'renamed'

            if selfAsDir :
                current['child' if VERSION_HDR == head_ln[:len(VERSION_HDR)] else 'offspring' ] = fn_loc
            else :
                debug('NotYetCovered: %s'%line)

            fn_loc = m.group(2).strip()
            if '$' == fn_loc[0] : fn_loc = fn_loc[1:] +'/'
            current['renamed_to'] = fn_loc
            continue

        # Created
        if 'Created' == line and '1' == current.get('version') :
            current['verb'] = 'created'

        if line in ['Labeled'] :
            continue # known line but useless
    
    __flush_current()
    file_hist.reverse()
    return fn_ret, file_hist

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
                debug('buildup_history() merged step: %s' %step) # TESTCODE
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

            debug('buildup_history() stepped %s> %s' %(filepath, step)) # TESTCODE

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
            debug('buildup_history() merged step: %s' %step) # TESTCODE
            # last_asof = max(last_asof, step.get('asof', ''))
            step=None
            
    return journal_merged

# ---------------------------------------
def associateActivity(filepath, **kwargs) :
    return [(filepath, kwargs.get('version',''))]

########################################################################
import getopt

if __name__ == '__main__':

    if len(sys.argv) <2:
        # sys.argv = [ sys.argv[0]] + "-t d:\\temp\\vss2git_top -d D:/temp/vss/CTFLib -u build -p nightly".split(' ') # for X1Y3
        sys.argv = [ sys.argv[0]] + "-t d:\\temp\\vss2git_top -d W:/vss/DSE1_TianShan.2.8 -u build -p nightly".split(' ') # for X1Y3
        pass

    ss_env = {
        'SSDIR':  os.environ.get('SSDIR', 'D:/temp/vss/CTFLib'),
        'SSUSER': os.environ.get('SSUSER', 'build'),
        'SSPWD':  os.environ.get('SSPWD', 'nightly'),
    }

    local_top = os.environ.get('VSS2GIT_TOP', 'd:\\temp\\vss2git_top')

    try:
        opts, args = getopt.getopt(sys.argv[1:], "t:d:u:p:", ["local-top=","ss-database=","ss-user=","ss-passwd="])
    except getopt.GetoptError :
        print('vss2git.py -t <local-top> -d <ss-database> -u <ss-user> -p <ss-passwd>')
        sys.exit(2)

    for opt, optv in opts:
        if opt in ("-t", "--local-top") :
            local_top = optv
            continue
        if opt in ("-d", "--ss-database") :
            ss_env['SSDIR'] = optv
        if opt in ("-u", "--ss-user") :
            ss_env['SSUSER'] = optv
            continue
        if opt in ("-p", "--ss-passwd") :
            ss_env['SSPWD'] = optv
            continue

    # apply the final SS vars onto env
    for var,v in ss_env.items() : os.environ[var] =v

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
    # debug('\n'.join(files))
    # exit(0)
    only_on_self =True
    # only_on_self =False
    f_ret, hist = history_of_file('$/', only_on_self) # hist on top
    # f_ret, hist = history_of_file('$/CTFLib/V2.0/CTFLib2.sln', only_on_self) # ever renamed
    # f_ret, hist = history_of_file('$/CTFLib/V3.0-SEAC/CTFTest/ctfTest3.0.suo', only_on_self) # ever deleted
    # f_ret, hist = history_of_file('$/CTFLib/build/buildbatch.txt', only_on_self) # long hist
    # f_ret, hist = history_of_file('$/CTFLib/build/', only_on_self) # long hist
    # f_ret, hist = history_of_file('$/MCDriver/MCCGDriver/MCCGDriver.rc')
    # debug('\n'*2+f_ret+'>'*40)
    # debug('\n'.join([str(i) for i in hist]))
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
        # exec_cmd('if not exist "%s" mkdir "%s"' %(subdir, subdir)) # TESTCODE
        # exec_cmd('if exist "%s" del /q "%s"' %(localfn, localfn)) # TESTCODE
        # if not os.path.isdir(subdir) : 
        #     pathlib.Path(os.path.relpath(subdir)).mkdir(parents=True, exist_ok=True) 
        return os.path.relpath(localfn)

    def __ss_get_to_local(sspath, ssver) :
        localfn = __to_localfile(sspath[2:])
        subdir = os.path.dirname(localfn) if '/'!=localfn[-1] else localfn
        subdir = os.path.relpath(subdir)
        if not os.path.isdir(subdir) : 
            pathlib.Path(os.path.realpath(subdir)).mkdir(parents=True, exist_ok=True) 

        bn = os.path.basename(localfn)
        subcmds = []
        subcmds.append('if not exist "%s" mkdir "%s"' %(subdir, subdir))
        subcmds.append('if exist "%s" del /q/f "%s"' %(localfn, localfn))
        subcmds.append('if exist ".\%s" move ".\%s" ".\%s~"' %(bn, bn, bn))
        subcmds.append(SS_EXE + ' GET %s -V%s' % (sspath, ssver))
        subcmds.append('move /Y ".\%s" "%s"' %(bn, subdir+'\\'))
        subcmds.append('if exist ".\%s~" move ".\%s~" ".\%s"' %(bn, bn, bn))
        # exec_cmd(' && '.join(subcmds))
        for i in subcmds : exec_cmd(i)

        return localfn

    for step in journal :
        # debug(step)
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
                # localfn = localfn(sspath[2:])
                # sscmd  = 'GET %s -V%s > %s' % (sspath, ssver, localfn)
                # exec_ss(sscmd)
                localfn = __ss_get_to_local(sspath, ssver)
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
                if '/' == sspath[-1] : continue  # ignore subdirs
                localfn = __ss_get_to_local(sspath, ssver)
                # sscmd  = 'GET %s -V%s > %s' % (sspath, ssver, localfn)
                # exec_ss(sscmd)
                gitcmd = 'add -f %s' % localfn
                bth_files.append(localfn)
                exec_git(gitcmd)
            continue

        debug('NotYetCovered: %s'%step)


    # debug('\n'*2+'>'*40)
    # debug('\n'.join([str(i) for i in journal]))

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

'''


