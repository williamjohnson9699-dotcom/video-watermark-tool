import os, sys, re, time, queue, threading, subprocess, tempfile, random
from PIL import ImageOps
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
FLAGS=subprocess.CREATE_NO_WINDOW

def probe(source):
    r=subprocess.run([str(ROOT/'ffmpeg.exe'),'-hide_banner','-i',str(source)],capture_output=True,encoding='utf-8',errors='replace',creationflags=FLAGS)
    line=next((s for s in r.stderr.splitlines() if 'Video:' in s),'')
    m=re.search(r'\b(\d{2,5})x(\d{2,5})\b',line)
    if not m: raise ValueError('无法读取视频尺寸')
    w,h=map(int,m.groups()); rot=re.search(r'rotation of\s+(-?[\d.]+)',r.stderr)
    if rot and round(float(rot[1]))%180: w,h=h,w
    d=re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)',r.stderr)
    return w,h,sum(float(v)*n for v,n in zip(d.groups(),(3600,60,1))) if d else 0

def stamp(path,text,font,size,color,alpha,w,h):
    f=ImageFont.truetype(font,size); b=f.getbbox(text,stroke_width=2)
    im=Image.new('RGBA',(b[2]-b[0]+12,b[3]-b[1]+12)); a=round(alpha*255/100)
    rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
    ImageDraw.Draw(im).text((6-b[0],6-b[1]),text,font=f,fill=(*rgb,a),stroke_width=2,stroke_fill=(0,0,0,a))
    ratio=min(1,max(1,w-32)/im.width,max(1,h-32)/im.height)
    if ratio<1: im=im.resize((max(1,int(im.width*ratio)),max(1,int(im.height*ratio))),Image.Resampling.LANCZOS)
    im.save(path)

def image_events(tmp, images, width_percent, alpha, seconds, w, h, duration, rng=None):
    if duration < 1.2:
        raise ValueError('图片水印需要至少 1.2 秒的视频，以保证六次出现均可见。')
    rng = rng or random.SystemRandom()
    slot = duration / 6
    visible = min(seconds, slot * .65)
    events = []
    for i in range(6):
        source = rng.choice(images)
        with Image.open(source) as original:
            im = ImageOps.exif_transpose(original).convert('RGBA')
        ratio = min(w * width_percent / 100 / im.width, (h-32)/im.height, (w-32)/im.width)
        im = im.resize((max(1, round(im.width*ratio)), max(1, round(im.height*ratio))), Image.Resampling.LANCZOS)
        im.putalpha(im.getchannel('A').point(lambda x: round(x * alpha / 100)))
        path = Path(tmp) / f'image_{i}.png'; im.save(path)
        start = i*slot + rng.uniform(slot*.05, slot-visible-slot*.05)
        x = rng.randint(16, max(16, w-im.width-16)); y = rng.randint(16, max(16, h-im.height-16))
        events.append(dict(path=path, start=start, end=start+visible, x=x, y=y, source=str(source)))
    return events

def command(source, png, output, speed, events=None, top_png=None, top_margin=0):
    args = [str(ROOT/'ffmpeg.exe'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-i', str(source)]
    graph=[]; current='0:v:0'; index=1
    if png is not None:
        args += ['-loop','1','-i',str(png)]
        x=f"16+abs(mod(t*{speed}+0.25*max(1,main_w-overlay_w-32),2*max(1,main_w-overlay_w-32))-max(1,main_w-overlay_w-32))"
        y=f"16+abs(mod(t*{speed*.73}+0.65*max(1,main_h-overlay_h-32),2*max(1,main_h-overlay_h-32))-max(1,main_h-overlay_h-32))"
        graph.append(f"[{current}][{index}:v:0]overlay=x='{x}':y='{y}':eval=frame:shortest=1[text]")
        index+=1; current='text'
    for i, event in enumerate(events or []):
        args += ['-loop','1','-i',str(event['path'])]
        graph.append(f"[{current}][{index}:v:0]overlay=x={event['x']}:y={event['y']}:shortest=1:enable='gte(t,{event['start']:.6f})*lt(t,{event['end']:.6f})'[image{i}]")
        current=f'image{i}'; index+=1
    if top_png is not None:
        args += ['-loop','1','-i',str(top_png)]
        graph.append(f"[{current}][{index}:v:0]overlay=x=(main_w-overlay_w)/2:y='min({top_margin},main_h-overlay_h)':shortest=1[top]")
        current='top'
    graph.append(f'[{current}]pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p[v]')
    return args + ['-filter_complex_threads','1','-filter_complex',';'.join(graph),'-map','[v]','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-b:a','192k','-movflags','+faststart','-shortest','-progress','pipe:1','-nostats','-n',str(output)]

def make_intro(source, stop):
    source=Path(source)
    duration=probe(source)[2]
    if duration<=0: raise ValueError('无法读取成品时长，已保留完整水印视频。')
    length=min(15.0,duration); start=random.SystemRandom().uniform(0,max(0,duration-length))
    target=source.with_name(source.stem+'_片头.mp4'); n=2
    while target.exists():
        target=source.with_name(source.stem+f'_{n}_片头.mp4'); n+=1
    fd,temp=tempfile.mkstemp(prefix='intro_',suffix='.mp4',dir=source.parent); os.close(fd)
    partial=Path(temp)
    try:
        args=[str(ROOT/'ffmpeg.exe'),'-hide_banner','-loglevel','error','-nostdin','-ss',f'{start:.6f}','-i',str(source),'-t',f'{length:.6f}','-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-b:a','192k','-movflags','+faststart','-y',str(partial)]
        with tempfile.TemporaryFile() as err:
            process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=err,creationflags=FLAGS)
            while process.poll() is None:
                if stop.wait(.1):
                    process.terminate(); process.wait(); raise RuntimeError('片头生成已停止，完整水印视频已保留。')
            if process.returncode:
                err.seek(0); raise RuntimeError('片头生成失败，完整水印视频已保留：'+err.read().decode('utf-8',errors='replace')[-1200:])
        partial.rename(target)
        return target,start,length
    finally:
        partial.unlink(missing_ok=True)

class App:
    def __init__(self,root):
        self.root=root; root.title('批量视频水印 v4.1 · 按视频选择片头 · 顶部固定 / 反弹文字 / 随机图片'); root.geometry('940x800'); root.minsize(850,740)
        self.files=[]; self.events=queue.Queue(); self.stop=threading.Event(); self.running=False; self.controls=[]; self.color='#FFFFFF'
        self.intro_files=set()
        self.top_enabled=tk.BooleanVar(value=True); self.top_text=tk.StringVar(value='顶部固定文字'); self.top_size=tk.IntVar(value=5); self.top_alpha=tk.IntVar(value=80); self.top_margin=tk.DoubleVar(value=2); self.top_color='#FFFFFF'
        self.images=[]; self.text_enabled=tk.BooleanVar(value=True); self.image_enabled=tk.BooleanVar(value=True)
        self.image_seconds=tk.DoubleVar(value=3); self.image_size=tk.IntVar(value=18); self.image_alpha=tk.IntVar(value=80); self.image_label=tk.StringVar(value='尚未选择图片')
        self.text=tk.StringVar(value='我的水印'); self.size=tk.IntVar(value=5); self.alpha=tk.IntVar(value=60); self.speed=tk.IntVar(value=100)
        self.dest=tk.StringVar(value=str(ROOT/'已处理视频')); self.font=tk.StringVar(value='C:/Windows/Fonts/msyh.ttc'); self.status=tk.StringVar(value='请添加视频，原视频会保留。')
        ttk.Style().configure('.',font=('Microsoft YaHei UI',10))
        f=ttk.Frame(root,padding=20); f.pack(fill='both',expand=True)
        ttk.Label(f,text='批量视频水印',font=('Microsoft YaHei UI',22,'bold')).pack(anchor='w')
        ttk.Label(f,text='顶部固定文字、反弹文字、随机图片，三种水印可独立开关。').pack(anchor='w',pady=(4,12))
        bar=ttk.Frame(f); bar.pack(fill='x')
        for label,fn in [('添加视频',self.add),('移除选中',self.remove),('清空列表',self.clear),('生成片头：标记选中',lambda:self.mark_intro(True)),('取消片头：选中',lambda:self.mark_intro(False))]: self.button(bar,label,fn).pack(side='left',padx=(0,8))
        self.list=tk.Listbox(f,height=5,selectmode='extended',exportselection=False); self.list.pack(fill='x',pady=8)
        tabs=ttk.Notebook(f); tabs.pack(fill='x',pady=6)
        top_tab=ttk.Frame(tabs,padding=10); text_tab=ttk.Frame(tabs,padding=10); image_tab=ttk.Frame(tabs,padding=10)
        tabs.add(top_tab,text='顶部固定文字（新增）'); tabs.add(text_tab,text='反弹文字 / 字体 / 输出'); tabs.add(image_tab,text='随机图片（六次）')
        enabled=ttk.Checkbutton(top_tab,text='启用顶部固定文字（全程显示，顶部居中）',variable=self.top_enabled); enabled.pack(anchor='w'); self.controls.append(enabled)
        top_grid=ttk.Frame(top_tab); top_grid.pack(fill='x',pady=8); top_grid.columnconfigure(1,weight=1)
        for row,(label,var) in enumerate([('顶部文字',self.top_text),('字号（视频高度 %，1–20）',self.top_size),('不透明度（1–100）',self.top_alpha),('距顶部（视频高度 %，0–30）',self.top_margin)]):
            ttk.Label(top_grid,text=label).grid(row=row,column=0,sticky='w',pady=5)
            entry=ttk.Entry(top_grid,textvariable=var); entry.grid(row=row,column=1,sticky='ew',padx=10); self.controls.append(entry)
        self.button(top_grid,'顶部文字颜色',self.pick_top_color).grid(row=0,column=2)
        ttk.Label(top_tab,text='顶部文字始终固定居中；字体与反弹文字共用，可在第二个选项卡设置。').pack(anchor='w')
        grid=ttk.Frame(text_tab); grid.pack(fill='x'); grid.columnconfigure(1,weight=1)
        for row,(label,var) in enumerate([('水印文字',self.text),('字号（画面高度 %，1–20）',self.size),('不透明度（5–100）',self.alpha),('速度（像素 / 秒，10–600）',self.speed),('字体文件',self.font),('输出文件夹',self.dest)]):
            ttk.Label(grid,text=label).grid(row=row,column=0,sticky='w',pady=5)
            e=ttk.Entry(grid,textvariable=var); e.grid(row=row,column=1,sticky='ew',padx=10); self.controls.append(e)
        self.button(grid,'文字颜色',self.pick_color).grid(row=1,column=2)
        self.button(grid,'选择字体',self.pick_font).grid(row=4,column=2)
        self.button(grid,'浏览',self.pick_dest).grid(row=5,column=2)
        options=ttk.LabelFrame(image_tab,text='图片水印 · 每个视频固定随机出现 6 次',padding=8); options.pack(fill='x',pady=(10,0))
        switches=ttk.Frame(options); switches.pack(fill='x')
        for label,var in [('启用反弹文字',self.text_enabled),('启用随机图片',self.image_enabled)]:
            c=ttk.Checkbutton(switches,text=label,variable=var); c.pack(side='left',padx=(0,16)); self.controls.append(c)
        self.button(switches,'选择一张或多张图片',self.pick_images).pack(side='left')
        ttk.Label(options,textvariable=self.image_label).pack(anchor='w',pady=4)
        settings=ttk.Frame(options); settings.pack(fill='x')
        for label,var in [('每次秒数（0.1–30）',self.image_seconds),('宽度 %（1–80）',self.image_size),('不透明度（1–100）',self.image_alpha)]:
            ttk.Label(settings,text=label).pack(side='left'); e=ttk.Entry(settings,textvariable=var,width=6); e.pack(side='left',padx=(4,12)); self.controls.append(e)
        ttk.Label(options,text='时间、位置与图片随机；六段互不重叠，短视频自动缩短显示时长。').pack(anchor='w',pady=(4,0))
        self.canvas=tk.Canvas(f,height=85,bg='#152333',highlightthickness=0); self.canvas.pack(fill='x',pady=(12,4))
        ttk.Label(f,text='运动示意 · 实际大小和透明度以导出为准；文字过长时自动缩小。',foreground='#666666').pack(anchor='w')
        bar=ttk.Frame(f); bar.pack(fill='x',pady=12)
        self.button(bar,'开始批量处理',self.start).pack(side='left')
        self.cancel=ttk.Button(bar,text='停止处理',command=self.stop.set,state='disabled'); self.cancel.pack(side='left',padx=10)
        ttk.Button(bar,text='打开输出文件夹',command=self.open_dest).pack(side='right')
        ttk.Label(f,text='仅列表中带【生成片头】标记的视频额外导出随机 15 秒片头；默认均不生成。').pack(anchor='w')
        self.progress=ttk.Progressbar(f,maximum=100); self.progress.pack(fill='x')
        ttk.Label(f,textvariable=self.status,wraplength=800).pack(anchor='w',pady=8)
        self.log=tk.Text(f,height=4,state='disabled'); self.log.pack(fill='both',expand=True)
        root.protocol('WM_DELETE_WINDOW',self.close); self.animate(); self.poll()
    def button(self,parent,label,fn):
        b=ttk.Button(parent,text=label,command=fn); self.controls.append(b); return b
    def add(self):
        for p in filedialog.askopenfilenames(filetypes=[('视频','*.mp4 *.mov *.mkv *.avi *.webm *.wmv *.m4v *.ts *.flv'),('所有文件','*.*')]):
            if p not in self.files: self.files.append(p); self.list.insert('end',p)
    def remove(self):
        for i in reversed(self.list.curselection()): self.intro_files.discard(self.files.pop(i)); self.list.delete(i)
    def clear(self): self.files.clear(); self.intro_files.clear(); self.list.delete(0,'end')
    def mark_intro(self,enabled):
        selected=self.list.curselection()
        for i in selected:
            path=self.files[i]
            if enabled: self.intro_files.add(path)
            else: self.intro_files.discard(path)
            self.list.delete(i); self.list.insert(i,('【生成片头】 ' if enabled else '')+path)
        for i in selected: self.list.selection_set(i)
        self.status.set(f'已标记 {sum(p in self.intro_files for p in self.files)} 个视频生成片头，其余只输出完整水印视频。')
    def pick_images(self):
        paths=filedialog.askopenfilenames(filetypes=[('图片','*.png *.jpg *.jpeg *.webp *.bmp'),('所有文件','*.*')])
        if paths:
            self.images=list(paths); self.image_enabled.set(True); self.image_label.set(f'已选择 {len(paths)} 张：'+ '、'.join(Path(p).name for p in paths)[:90])
    def pick_top_color(self):
        color=colorchooser.askcolor(self.top_color)[1]
        if color: self.top_color=color
    def pick_color(self):
        c=colorchooser.askcolor(self.color)[1]
        if c: self.color=c
    def pick_font(self):
        p=filedialog.askopenfilename(initialdir='C:/Windows/Fonts',filetypes=[('字体','*.ttf *.ttc *.otf')])
        if p: self.font.set(p)
    def pick_dest(self):
        p=filedialog.askdirectory()
        if p: self.dest.set(p)
    def open_dest(self):
        try: p=Path(self.dest.get()); p.mkdir(parents=True,exist_ok=True); os.startfile(p)
        except Exception as e: messagebox.showerror('无法打开',str(e))
    def animate(self):
        try:
            self.canvas.delete('all'); t=time.monotonic(); v=self.speed.get()*.3
            item=self.canvas.create_text(0,0,anchor='nw',text=self.text.get(),fill=self.color,font=('Microsoft YaHei UI',max(10,int(self.size.get()*2.2)),'bold'))
            b=self.canvas.bbox(item); dx=max(1,self.canvas.winfo_width()-(b[2]-b[0])-20); dy=max(1,85-(b[3]-b[1])-20)
            self.canvas.coords(item,10+abs(t*v%(2*dx)-dx),10+abs(t*v*.73%(2*dy)-dy))
        except (ValueError,tk.TclError,TypeError): pass
        self.root.after(33,self.animate)
    def start(self):
        try:
            if not self.files: raise ValueError('请先添加视频。')
            if self.text_enabled.get() and not self.text.get().strip(): raise ValueError('请输入水印文字。')
            if len(self.text.get())>500: raise ValueError('文字请控制在 500 字以内。')
            for v,lo,hi in [(self.size.get(),1,20),(self.alpha.get(),5,100),(self.speed.get(),10,600)]:
                if not lo<=v<=hi: raise ValueError('参数超出标注范围。')
            if (self.text_enabled.get() or self.top_enabled.get()) and not Path(self.font.get()).is_file(): raise ValueError('请选择有效字体文件。')
            if not self.dest.get().strip(): raise ValueError('请选择输出文件夹。')
            dest=Path(self.dest.get()); dest.mkdir(parents=True,exist_ok=True)
            if not (ROOT/'ffmpeg.exe').is_file(): raise ValueError('缺少 ffmpeg.exe。')
            if not self.text_enabled.get() and not self.image_enabled.get() and not self.top_enabled.get(): raise ValueError('请至少启用一种水印。')
            if self.image_enabled.get():
                if not self.images: raise ValueError('请先选择水印图片，或关闭随机图片。')
                for v,lo,hi in [(self.image_seconds.get(),.1,30),(self.image_size.get(),1,80),(self.image_alpha.get(),1,100)]:
                    if not lo<=v<=hi: raise ValueError('图片水印参数超出范围。')
                for path in self.images:
                    with Image.open(path) as im: im.verify()
            if self.top_enabled.get():
                if not self.top_text.get().strip(): raise ValueError('请输入顶部固定文字。')
                if len(self.top_text.get())>500: raise ValueError('顶部文字请控制在 500 字以内。')
                for v,lo,hi in [(self.top_size.get(),1,20),(self.top_alpha.get(),1,100),(self.top_margin.get(),0,30)]:
                    if not lo<=v<=hi: raise ValueError('顶部文字参数超出范围。')
            cfg=(self.text.get(),self.font.get(),self.size.get(),self.color,self.alpha.get(),self.speed.get(),dict(text_enabled=self.text_enabled.get(),image_enabled=self.image_enabled.get(),images=list(self.images),seconds=self.image_seconds.get(),width=self.image_size.get(),alpha=self.image_alpha.get(),top_enabled=self.top_enabled.get(),top_text=self.top_text.get(),top_size=self.top_size.get(),top_alpha=self.top_alpha.get(),top_margin=self.top_margin.get(),top_color=self.top_color,intro_files=list(self.intro_files)))
        except Exception as e: messagebox.showerror('请检查设置',str(e)); return
        self.running=True; self.stop.clear(); self.progress['value']=0
        for c in self.controls: c.configure(state='disabled')
        self.cancel.configure(state='normal')
        threading.Thread(target=self.process,args=(list(self.files),dest,cfg),daemon=True).start()
    def process(self,files,dest,cfg):
        ok=bad=0
        try:
            for i,source in enumerate(files):
                if self.stop.is_set(): break
                target=dest/(Path(source).stem+'_水印.mp4'); n=2
                while target.exists(): target=dest/(Path(source).stem+f'_水印_{n}.mp4'); n+=1
                partial=target.with_name(target.stem+'.processing.mp4')
                while partial.exists(): partial=partial.with_name(partial.stem+'_new.mp4')
                self.events.put(('status',f'正在处理 {i+1}/{len(files)}：{Path(source).name}'))
                try:
                    w,h,duration=probe(source)
                    with tempfile.TemporaryDirectory(prefix='watermark_',dir=ROOT) as tmp:
                        png=Path(tmp)/'stamp.png'; text,font,size,color,alpha,speed=cfg[:6]
                        options=cfg[6] if len(cfg)>6 else dict(text_enabled=True,image_enabled=False)
                        if options['text_enabled']: stamp(png,text,font,max(12,round(h*size/100)),color,alpha,w,h)
                        else: png=None
                        events=image_events(tmp,options['images'],options['width'],options['alpha'],options['seconds'],w,h,duration) if options['image_enabled'] else []
                        if events: self.events.put(('log',Path(source).name+' 图片出现秒数：'+', '.join(f"{e["start"]:.2f}–{e["end"]:.2f}" for e in events)))
                        top_png=None; top_margin=0
                        if options.get('top_enabled'):
                            top_png=Path(tmp)/'top.png'
                            stamp(top_png,options['top_text'],font,max(12,round(h*options['top_size']/100)),options['top_color'],options['top_alpha'],w,h)
                            top_margin=round(h*options['top_margin']/100)
                        with open(Path(tmp)/'error.log','w+',encoding='utf-8') as err:
                            p=subprocess.Popen(command(source,png,partial,speed,events,top_png,top_margin),stdout=subprocess.PIPE,stderr=err,encoding='utf-8',errors='replace',creationflags=FLAGS)
                            def monitor(proc):
                                while proc.poll() is None:
                                    if self.stop.wait(.2):
                                        if proc.poll() is None: proc.terminate()
                                        return
                            threading.Thread(target=monitor,args=(p,),daemon=True).start()
                            for line in p.stdout:
                                if line.startswith('out_time_us=') and duration:
                                    try: self.events.put(('progress',(i+min(1,int(line.split('=')[1])/1e6/duration))/len(files)*100))
                                    except ValueError: pass
                            code=p.wait(); p.stdout.close()
                            if self.stop.is_set(): break
                            if code: err.seek(0); raise RuntimeError(err.read()[-1200:] or f'FFmpeg 错误 {code}')
                    partial.rename(target); self.events.put(('log','水印视频完成：'+target.name))
                    if source in options.get('intro_files',[]):
                        self.events.put(('status','正在生成随机 15 秒片头：'+target.name))
                        intro,start,length=make_intro(target,self.stop)
                        self.events.put(('log',f'片头完成：{intro.name}（从 {start:.2f} 秒开始，时长 {length:.2f} 秒）'))
                    ok+=1
                except Exception as e: bad+=1; self.events.put(('log',f'失败：{Path(source).name} — {e}'))
                finally:
                    if partial.exists(): partial.unlink()
                self.events.put(('progress',(i+1)/len(files)*100))
        finally: self.events.put(('done',f'{"已停止" if self.stop.is_set() else "处理结束"}：成功 {ok} 个，失败 {bad} 个。'))
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress': self.progress['value']=value
                elif kind=='log': self.log.configure(state='normal'); self.log.insert('end',value+'\n'); self.log.see('end'); self.log.configure(state='disabled')
                elif kind=='done':
                    self.running=False
                    for c in self.controls: c.configure(state='normal')
                    self.cancel.configure(state='disabled'); self.status.set(value)
                else: self.status.set(value)
        except queue.Empty: pass
        self.root.after(100,self.poll)
    def close(self):
        if self.running: self.stop.set(); self.status.set('正在停止，请稍候。'); self.root.after(250,self.close)
        else: self.root.destroy()

if __name__=='__main__': App(tk.Tk()).root.mainloop()

