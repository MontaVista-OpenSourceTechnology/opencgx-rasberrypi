#!/bin/bash -x 
export -n BBPATH
if [ -n "$BASH_SOURCE" ]; then
    THIS_SCRIPT=$BASH_SOURCE
elif [ -n "$ZSH_NAME" ]; then
    THIS_SCRIPT=$0
else
    THIS_SCRIPT="$(pwd)/setup.sh"
fi
if [ -z "$ZSH_NAME" ] && [ "$0" = "$THIS_SCRIPT" ]; then
   EXIT="exit"
else
   EXIT="return" 
fi
export PATH=$PATH
THIS_SCRIPT=$(readlink -f $THIS_SCRIPT)
TOPDIR=$(dirname $THIS_SCRIPT)
if [ "x$1" = "x" ] ;
then
	buildDir=$TOPDIR/project
        echo "$buildDir used as project." 2>&1
	echo "To change source $THIS_SCRIPT <builddir>" 2>&1
else
	buildDir=$1
fi
 
mkdir -p $buildDir
buildDir=$(readlink -f $buildDir)

REPO_CONFIG="\
LAYER@https://github.com/MontaVista-OpenSourceTechnology/poky.git;branch=thud;layer=meta \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/poky.git;branch=thud;layer=meta-poky \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/poky.git;branch=thud;layer=meta-yocto-bsp \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-oe \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-python \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-filesystems \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-networking \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-webserver \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-clang.git;branch=thud \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-virtualization.git;branch=thud \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-qa.git;branch=thud;layer=meta-qa-framework \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-qa.git;branch=thud;layer=meta-qa-testsuites \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-montavista-cgx.git;branch=thud;layer=qemu-bsp \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-montavista-cgx.git;branch=thud \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-perl \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-gnome \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-multimedia \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-openembedded.git;branch=thud;layer=meta-xfce \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-selinux.git;branch=thud \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-security.git;branch=thud \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-cgl.git;branch=thud;layer=meta-cgl-common \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-cloud-services.git;branch=thud \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-cloud-services.git;branch=thud;layer=meta-openstack \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-montavista-cgl.git;branch=thud \
LAYER@https://github.com/MontaVista-OpenSourceTechnology/meta-raspberrypi.git;branch=thud \
MACHINE@raspberrypi3-64 \
DISTRO@mvista-cgx \
CONFIG@LICENSE_FLAGS_WHITELIST=commercial \
"
TOPDIR=$(dirname $THIS_SCRIPT)
buildtar=""
URL=""

for config in $REPO_CONFIG; do
    VAR=$(echo $config | cut -d @ -f 1)
    VAL=$(echo $config | cut -d @ -f 2)
    if [ "$VAR" = "URL" ] ; then
       URL=$VAL
       URLBASE=$(echo $URL | cut -d / -f 1-3)
       HOST=$(echo $URL | cut -d / -f 3)
    fi
done

export BUILD_TOOLS_LOCATION
export buildtar
$TOPDIR/bin/fetch-buildtools || $EXIT 1

source $TOPDIR/buildtools/environment-setup-*
if [ "$?" != "0" ] ; then
   $EXIT 1
fi

chmod 755 $TOPDIR/bin/*
if [[ ("x$URLBASE" != "x") && ( "$HOST" = "staging.support.mvista.com" || "$HOST" = "support.mvista.com") ]] ; then
   git config --global credential.$URLBASE.helper $TOPDIR/bin/git-credential-mvl
   git config --global http.$URLBASE.cookiefile $($TOPDIR/bin/mvl-fetch -c $URLBASE)
fi

if [ ! -e $TOPDIR/.drop ] ; then
   if [ ! -e $TOPDIR/.repo ] ; then
      pushd $TOPDIR 2>/dev/null 1>/dev/null
         git config pull.rebase True
         git submodule init || $EXIT 1
	 if [ -z "$GIT_RETRIES" ] ; then
            GIT_RETRIES=5
	 fi
	 if [ -z "$GIT_DELAY" ] ; then
            GIT_DELAY=10
	 fi
         GIT_COUNT=1
         while [ $GIT_COUNT -lt $GIT_RETRIES ] ; do
            git submodule update --remote
            if [ $? -eq 0 ] ; then
                 GIT_RETRIES=0
                 break
            fi
            GIT_COUNT=$(($GIT_COUNT + 1))
	    echo "git submodule update failed, sleeping for $GIT_DELAY seconds and retrying"
            sleep $GIT_DELAY
         done
         if [ $GIT_RETRIES != 0 ] ; then
            $EXIT 1
         fi
      popd  2>/dev/null 1>/dev/null
   else
      pushd $TOPDIR 2>/dev/null >/dev/null
         repo sync
      popd 2>/dev/null >/dev/null
   fi
fi

if [ -z "$TEMPLATECONF" -o ! -d "$TEMPLATECONF" ] ; then
    export TEMPLATECONF=$TOPDIR/layers/meta-montavista-cgx/conf
fi

source $TOPDIR/layers/poky/oe-init-build-env $buildDir 
if [ "$?" != "0" ] ; then
   $EXIT 1
fi
export BB_NO_NETWORK="1"
export LAYERS_RELATIVE="1"
if [ -z "$LOCAL_SOURCES" ] ; then
      LOCAL_SOURCES=1
fi
if [ -e $TOPDIR/.drop -o "$MAKEDROP" = "1" ] ; then
      LOCAL_SOURCES=1
fi
echo "# Do not modify, automatically generated" > conf/local-content.conf
echo >> conf/local-content.conf

for config in $REPO_CONFIG; do
    VAR=$(echo $config | cut -d @ -f 1)
    VAL=$(echo $config | cut -d @ -f 2)
    if [ "$VAR" = "LAYER" ] ; then
       layer=$(echo $VAL | cut -d \; -f 1)
       layerDir=$(basename $layer | sed s,.git,,)
       options=$(echo $VAL | cut -d \; -f 2-)
       sublayer=""
       for option in $(echo $options | sed s,\;,\ ,g); do
           if [ "$(echo $option | cut -d = -f 1)" = "layer" ] ; then
                sublayer=$(echo $option | cut -d = -f 2)
           fi
       done
       if [ "$MAKEDROP" != "1" ] ; then
          mkdir -p $buildDir/.layers
          if [ ! -e $buildDir/.layers/$layerDir-$sublayer ] ; then
             echo "adding $layerDir/$sublayer"
             bitbake-layers -F add-layer $TOPDIR/layers/$layerDir/$sublayer >/dev/null || $EXIT 1
             touch $buildDir/.layers/$layerDir-$sublayer
          fi
       fi
    fi
    if [ "$VAR" = "MACHINE" ] ; then
          echo "MACHINE ?= '$VAL'" >> conf/local-content.conf
          echo >> conf/local-content.conf
    fi
    if [ "$VAR" = "DISTRO" ] ; then
          echo "DISTRO ?= '$VAL'" >> conf/local-content.conf
          echo >> conf/local-content.conf
    fi
    if [ "$VAR" = "SOURCE" ] ; then
          META=""
          BRANCH="master"
          TREE=$(echo $VAL | cut -d \; -f 1)
          for option in $(echo $VAL | sed s,\;,\ ,g); do
              OVAR=$(echo $option | cut -d = -f 1) 
              OVAL=$(echo $option | cut -d = -f 2)
              if [ "$OVAR" = "meta" ] ; then
                    META=$OVAL
              fi
              if [ "$OVAR" = "branch" ] ; then
                    BRANCH=$OVAL
              fi
          done
          mkdir -p $TOPDIR/sources-export
          LSOURCE=$TOPDIR/sources/$(basename $TREE | sed s,.git,,)
          LSOURCE_EXPORT=$TOPDIR/sources-export/$(basename $TREE | sed s,.git,,)
          if [ ! -e $TOPDIR/.drop ] ; then
              pushd $LSOURCE 2>/dev/null >/dev/null
                     git checkout $BRANCH || $EXIT 1
                     git pull 2>/dev/null >/dev/null
              popd 2>/dev/null >/dev/null
              
              if [ ! -e $LSOURCE_EXPORT ] ; then
                 if [ "$BRANCH" = "master" ] ; then
                    git clone --bare $LSOURCE $LSOURCE_EXPORT
                 else
                    git clone -b $BRANCH --bare $LSOURCE $LSOURCE_EXPORT
                 fi
              else
                 pushd $LSOURCE_EXPORT 2>/dev/null >/dev/null
                     git fetch || $EXIT 1
                 popd 2>/dev/null >/dev/null
              fi
          fi
          DL_TREE="git://$TOPDIR/sources-export/$(basename $TREE | sed s,.git,,)"
          echo "$(echo $META)_TREE = '$DL_TREE'" >> conf/local-content.conf
          echo "$(echo $META)_BRANCH = '$BRANCH'" >> conf/local-content.conf
          echo "BB_HASHBASE_WHITELIST_append += \"$(echo $META)_TREE\"" >> conf/local-content.conf
          echo >> conf/local-content.conf
    fi
    if [ "$VAR" = "CONFIG" ] ; then
       option=$(echo $VAL | cut -d = -f 1)
       setting=$(echo $VAL | cut -d = -f 2)
       echo "$option ?= '$setting'" >> conf/local-content.conf
    fi   
done
if [ -n "$SOURCE_MIRROR_URL" ] ; then
   if [ -z "$(echo $SOURCE_MIRROR_URL | grep "://")" ] ; then
      # Assume file
      SOURCE_MIRROR_URL="file://$SOURCE_MIRROR_URL"
   fi
   echo "SOURCE_MIRROR_URL = '$SOURCE_MIRROR_URL'" >> conf/local-content.conf
   echo >> conf/local-content.conf
   SOURCE_MIRROR_URL=""
fi
if [ -n "$PROTECTED_SOURCE_URL" ] ; then 
   if [ -z "$(echo $PROTECTED_SOURCE_URL | grep "://")" ] ; then
      # Assume file
      PROTECTED_SOURCE_URL="file://$PROTECTED_SOURCE_URL"
   fi
   echo "PROTECTED_SOURCE_URL = '$PROTECTED_SOURCE_URL'" >> conf/local-content.conf
   echo >> conf/local-content.conf
   PROTECTED_SOURCE_URL=""
fi

if [ -n "$SSTATE_MIRRORS" ] ; then
   if [ -z "$(echo $SSTATE_MIRRORS | grep "://")" ] ; then
      # Assume file
      SSTATE_MIRRORS="file://$SSTATE_MIRRORS"
   fi
   echo "SSTATE_MIRRORS = 'file://.*  $SSTATE_MIRRORS/PATH \n '" >> conf/local-content.conf
   echo >> conf/local-content.conf
   SSTATE_MIRRORS=""
fi

export -n BB_NO_NETWORK
if [ "$MAKEDROP" != "1" ] ; then
   # Temporary waiting for proper bitbake integration: https://patchwork.openembedded.org/patch/144806/
   RELPATH=$(python -c "from os.path import relpath; print (relpath(\"$TOPDIR/layers\",\"$(pwd)\"))")
   sed -i conf/bblayers.conf -e "s,$TOPDIR/layers/,\${TOPDIR}/$RELPATH/,"
   
   if [ "$(readlink -f setup.sh)" = "$(readlink -f $TOPDIR/setup.sh)" ] ; then
      echo "Something went wrong. Exiting to prevent overwritting setup.sh"
      $EXIT 1
   fi
   SCRIPT_RELPATH=$(python -c "from os.path import relpath; print (relpath(\"$TOPDIR\",\"`pwd`\"))")
   cat > setup.sh << EOF
   if [ -n "\$BASH_SOURCE" ]; then
      THIS_SCRIPT=\$BASH_SOURCE
   elif [ -n "\$ZSH_NAME" ]; then
      THIS_SCRIPT=\$0
   else
      THIS_SCRIPT="\$(pwd)/setup.sh"
   fi
   PROJECT_DIR=\$(dirname \$(readlink -f \$THIS_SCRIPT))
   cd \$PROJECT_DIR
   source $SCRIPT_RELPATH/buildtools/environment-setup-*
   source $SCRIPT_RELPATH/layers/poky/oe-init-build-env \$PROJECT_DIR
EOF
   rm -rf tmp-glibc
else
   rm -rf tmp
   rm -rf $TOPDIR/buildtools
   touch $TOPDIR/.drop
   rm -rf $TOPDIR/project
fi
if [ "$EXIT" = "exit" ] ; then
   echo
   echo "=Setup Complete="
   echo
   echo "* Run the following to start building with your project:"
   echo "source $buildDir/setup.sh"
   echo "bitbake core-image-minimal"
   echo
else
   echo
   echo "=Setup Complete="
   echo
   echo "* To start building run the following:"
   echo "bitbake core-image-minimal"
   echo
   echo "* To re-setup your build environment for your build later, run:"
   echo "source $buildDir/setup.sh"
   echo
fi
echo "* To update your content sources run:"
if [ "$(readlink -f $buildDir)" = "$(readlink -f $TOPDIR/project)" ] ; then
      echo "source $TOPDIR/setup.sh"
else
      echo "source $TOPDIR/setup.sh $buildDir"
fi
echo
