#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
read -p "Which category? [sys]/ai: " category
if [ -z $category ];
then 
  category="sys"
fi
if !([ $category == "ai" ] || [ $category == "sys" ])
then
  echo "Invalid category: $category"
  exit
fi

read -p "Include CrossRef? y/[n]: " crossref_on
if [ -z $crossref_on ];
then 
  crossref_on="n"
fi
strict="--strict"
if [ $crossref_on == "y" ]
then
  strict=""
fi

$SCRIPT_DIR/.venv/bin/python arxiv.py -c $category $strict --onlynew --translate-title
read -p "Press ENTER to continue"
