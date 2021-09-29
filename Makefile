build:
	python3 setup.py bdist_wheel #--bdist-dir bdtmp --dist-dir dist
	rm -r pytuyo.egg-info
	rm -r build

init:
	sudo -H pip3 install -r requirements.txt

#test:
#	python3 tests/test.py
#
uninstall:
	sudo pip3 uninstall pytuyo -y

install: build uninstall
	sudo -H pip3 install --upgrade dist/$(shell ls -t dist/ | head -n 1)

clean:
	rm -rf dist

.PHONY: build init install uninstall clean
#.PHONY: test
