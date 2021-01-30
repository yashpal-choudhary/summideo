# Imports
import argparse
import os
import pysrt
import re
import subprocess
import sys
import math
import pytube
import six
from moviepy.editor import VideoFileClip, TextClip, ImageClip, concatenate_videoclips

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words

from sumy.summarizers.luhn import LuhnSummarizer
from sumy.summarizers.edmundson import EdmundsonSummarizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.summarizers.text_rank import TextRankSummarizer
from sumy.summarizers.lex_rank import LexRankSummarizer
import nltk
nltk.download('punkt')

SUMMARIZERS = {
    'LU': LuhnSummarizer,
    'ED': EdmundsonSummarizer,
    'LS': LsaSummarizer,
    'TR': TextRankSummarizer,
    'LR': LexRankSummarizer
}


def create_summary(filename, regions):
    subclips = []
    # obtain video
    input_video = VideoFileClip(filename)
    last_end = 0
    for (start, end) in regions:
        subclip = input_video.subclip(start, end)
        subclips.append(subclip)
        last_end = end

    return concatenate_videoclips(subclips)

def srt_item_to_range(item):
    start_s = item.start.hours*60*60 + item.start.minutes*60 + item.start.seconds + item.start.milliseconds/1000.
    end_s = item.end.hours*60*60 + item.end.minutes*60 + item.end.seconds + item.end.milliseconds/1000.
    return start_s, end_s

def srt_to_doc(srt_file):
    text = ''
    for index, item in enumerate(srt_file):
        ##print(item.text)
        if item.text.startswith("["): continue
        text += "(%d) " % index
        text += item.text.replace("\n", "").strip("...").replace(".", "").replace("?", "").replace("!", "")
        text += ". "
    return text

def total_duration_of_regions(regions):
    totalT=0
    for i in range(len(regions)):
        if(((regions[i])[1]-(regions[i])[0]) > 0):
            totalT=totalT+(regions[i])[1]-(regions[i])[0]
    return totalT

def summarize(srt_file, summarizer, n_sentences, language, bonusWords, stigmaWords):
    parser = PlaintextParser.from_string(srt_to_doc(srt_file), Tokenizer(language))

    if(summarizer == 'ED'):
        summarizer = EdmundsonSummarizer()

        with open(bonusWords,"r+") as f:
            bonus_wordsList = f.readlines()
            bonus_wordsList = [x.strip() for x in bonus_wordsList]
            f.close()
        with open(stigmaWords,"r+") as f:
            stigma_wordsList = f.readlines()
            stigma_wordsList = [x.strip() for x in stigma_wordsList]
            f.close()

        summarizer.bonus_words = (bonus_wordsList)
        summarizer.stigma_words = (stigma_wordsList)
        summarizer.null_words = get_stop_words(language)
    else:
        stemmer = Stemmer(language)
        summarizer = SUMMARIZERS[summarizer](stemmer)
        summarizer.stop_words = get_stop_words(language)

    ret = []
    summarizedSubtitles = []

    for sentence in summarizer(parser.document, n_sentences):
        index = int(re.findall("\(([0-9]+)\)", str(sentence))[0])
        item = srt_file[index]
        # print("item ",item)
        summarizedSubtitles.append(item)

        ret.append(srt_item_to_range(item))

    return ret,summarizedSubtitles

def find_summary_regions(srt_filename, summarizer, duration, language ,bonusWords,stigmaWords,videonamepart):
    srt_file = pysrt.open(srt_filename)

    clipList = list(map(srt_item_to_range,srt_file))

    avg_subtitle_duration = total_duration_of_regions(clipList)/len(srt_file)

    n_sentences = duration / avg_subtitle_duration
    print("nsentance : "+str(n_sentences))

    [summary,summarizedSubtitles] = summarize(srt_file, summarizer, n_sentences, language, bonusWords, stigmaWords)
    total_time = total_duration_of_regions(summary)
    print("total_time : "+str(total_time))
    try_higher = total_time < duration
    prev_total_time = -1
    if try_higher:
        while total_time < duration:
            if(prev_total_time==total_time):
                print("1 : Maximum summarization time reached")
                break
            print("1 : total_time : duration "+str(total_time)+" "+str(duration))
            n_sentences += 1
            [summary,summarizedSubtitles] = summarize(srt_file, summarizer, n_sentences, language, bonusWords, stigmaWords)
            prev_total_time=total_time
            total_time = total_duration_of_regions(summary)
    else:
        while total_time > duration:
            if(n_sentences<=2):
                print("2 : Minimum summarization time reached")
                break
            print("2 : total_time : duration "+str(total_time)+str(duration))
            n_sentences -= 1
            [summary,summarizedSubtitles] = summarize(srt_file, summarizer, n_sentences, language, bonusWords, stigmaWords)
            total_time = total_duration_of_regions(summary)

    print("************ THis is summary array *********")
    print(summary)
    print("**********************************")

    print("************************THis is summarizedSubtitles array *******************")
    print(summarizedSubtitles)
    print("**********************************************************")
    subs=[]
    starting=0
    sub_rip_file = pysrt.SubRipFile()
    for index,item in enumerate(summarizedSubtitles):
        newSubitem=pysrt.SubRipItem()
        newSubitem.index=index
        newSubitem.text=item.text
        duration=summary[index][1]-summary[index][0]
        ending=starting+duration
        newSubitem.start.seconds=starting
        newSubitem.end.seconds=ending
        sub_rip_file.append(newSubitem)
        starting=ending

    print(sub_rip_file)

    # print(subs)


    path = videonamepart+".srt"
    with open(path,"w+") as sf:
        for i in range(0,len(sub_rip_file)):
            sf.write(str(sub_rip_file[i]))
            sf.write("\n")
    sf.close()

    return summary


def summarizeVideo(videoName,subtitleName,summType,summTime,bonusWords,stigmaWords):

    video=videoName

    subtitle=subtitleName

    summarizerName=summType
    duration=int(summTime)
    language='english'
    base, ext = os.path.splitext(video)
    print("base : "+str(base))
    videonamepart = "{0}_".format(base)
    commonName = videonamepart +str(summarizerName)+"_summarized"
    videoUrl=commonName+".mp4"

    regions = find_summary_regions(subtitle,
                                   summarizer=summarizerName,
                                   duration=duration,
                                   language=language,
                                   bonusWords=bonusWords,
                                   stigmaWords=stigmaWords,
                                   videonamepart=commonName
                                   )
    print((regions[-1])[1])
    if((regions[-1])[1]==0):
        regions = regions[:-1]
    print("regions : ")
    print(regions)

    summary = create_summary(video,regions)
    # Converting to video
    summary.to_videofile(
        videoUrl,
        codec="libx264",
        temp_audiofile="temp.m4a",
        remove_temp=True,
        audio_codec="aac",
    )
    return commonName
