package list.news.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class NewsCrawlerService {

    public List<String> getPopularNewsUrls() {
        List<String> urls = new ArrayList<>();

        try {
            Document doc = Jsoup.connect("https://news.einfomax.co.kr/news/articleList.html?view_type=sm").get();

            //인기 뉴스 영역
            Elements links = doc.select("div#skin-15 div.item > a");

            for(Element link : links) {
                String href = link.attr("href");
                if(!href.startsWith("http")) {
                    href = "http://news.einfomax.co.kr" + href;
                }
                urls.add(href);
            }
        } catch (IOException e) {
            e.printStackTrace();
        }

        return urls;
    }

    //테스트용 main 메서드
    public static void main(String[] args) {
        NewsCrawlerService crawler = new NewsCrawlerService();
        List<String> newsUrls = crawler.getPopularNewsUrls();

        System.out.println("인규 뉴스 목록");
        for(String url : newsUrls) {
            System.out.println(url);
        }
    }

}
