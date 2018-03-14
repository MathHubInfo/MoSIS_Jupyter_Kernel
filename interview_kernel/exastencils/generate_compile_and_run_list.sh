#!/bin/bash

if [[ "$OSTYPE" == "linux-gnu" ]]; then
  platform=lib/linux.platform
elif [[ "$OSTYPE" == "darwin"* ]]; then
  platform=lib/mac.platform
fi

source examples.sh

echo generating code for $configList
echo

mkdir Debug 2>/dev/null

for config in $configList; do
  echo generating $config ...
  printf "\033]2;generating $config\007"
  TIME=$( time java -cp compiler.jar Main $config.settings $config.knowledge $platform > ./Debug/${config##*/}_generateResult.txt; exit ${PIPESTATUS[0]}
)
  RET=$?
  echo $TIME
  if [[ "$RET" -eq "0" ]]; then
    printf "\033[32m\033[1mSuccess\033[0m"
  else
    printf "\033[31m\033[1mFailure\033[0m"
  fi
  echo
done
printf "\033]0;\a"



echo compiling code for $configList
echo 

callPath=$(pwd)

for config in $configList; do
  echo compiling $config ...
  printf "\033]2;compiling $config\007"
  cd $callPath/generated/${config##*/}
  TIME=$( time make -j 8 > $callPath/Debug/${config##*/}_makeResult.txt; exit ${PIPESTATUS[0]} )
  RET=$?
  echo $TIME
  if [[ "$RET" -eq "0" ]]; then
    printf "\033[32m\033[1mSuccess\033[0m"
  else
    printf "\033[31m\033[1mFailure\033[0m"
  fi
  echo 
done
printf "\033]0;\a"

echo running executables for $configList
echo

callPath=$(pwd)

for config in $configList; do
  echo running $config ...
  printf "\033]2;running $config\007"
  cd $callPath/generated/${config##*/}
  time ./exastencils
  echo
done
printf "\033]0;\a"