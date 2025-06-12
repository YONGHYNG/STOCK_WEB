package list.news.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class NewsService {

    public List<String> getNewsTitles() throws IOException {
        String url = "https://finance.naver.com/news/news_list.naver?mode=LSTD&section_id=101&section_id2=258&type=1";
        Document doc = Jsoup.connect(url).get();

        Elements titleElements = doc.select("dd.articleSubject > a");

        List<String> titles = new ArrayList<>();
        for(Element e: titleElements) {
            String title = e.text();
            titles.add(title);

        }
        return titles;
    }
}
